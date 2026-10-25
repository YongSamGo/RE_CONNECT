"""실제 추천 HTTP 응답을 가상 확정본·SQLite 공개본으로 만든다. 외부 서버는 없다."""

import asyncio
import json
from contextlib import nullcontext
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core.config import Settings  # noqa: E402

with patch("app.core.config.get_settings", return_value=Settings(_env_file=None, app_env="test")):
    from tests.test_journeys import app_for_test
    from tests.test_roles import MemoryRolesStore, role

import httpx  # noqa: E402
from sqlalchemy import insert  # noqa: E402
from app.contracts.time import utc_now  # noqa: E402
from app.modules.journeys.service import JourneyService  # noqa: E402
from app.modules.opportunities.repository import SqlPublicOpportunityRepository  # noqa: E402
from app.modules.opportunities.service import PublicOpportunityService  # noqa: E402
from app.modules.recommendations.service import RecommendationService  # noqa: E402
from app.modules.eligibility.service import EligibilityService  # noqa: E402
from app.modules.drafts.service import DraftService  # noqa: E402
from app.modules.drafts.repository import DraftPermit  # noqa: E402
from app.core.business_errors import AppError  # noqa: E402
from app.modules.roles.repository import SQLRoleCatalog  # noqa: E402
from app.modules.roles.service import RoleService  # noqa: E402
from app.persistence.operations import RoleDefinition  # noqa: E402
from tests.persistence_helpers import open_test_database  # noqa: E402
from tests.test_consents import csrf  # noqa: E402
from tests.test_profile_confirmation import ready_edit  # noqa: E402
from tests.test_public_opportunities import seeded  # noqa: E402


class MemoryDraftStore:
    """HTTP/계약만 검증하는 체험 대역. 원자성은 실제 Redis 백엔드 시험의 책임이다."""
    def __init__(self):
        self.drafts = {}

    async def reserve(self, session, journey_id, key, fingerprint, revision, profile_version, notice=''):
        return DraftPermit(key, 'test-execution', uuid4(), revision, profile_version, uuid4(), notice)

    async def complete(self, session, journey_id, permit, draft):
        self.drafts[draft.draft_id] = draft
        return draft

    async def read(self, session, journey_id, draft_id):
        if draft_id not in self.drafts:
            raise AppError('NOT_FOUND')
        return self.drafts[draft_id]

    async def mutate(self, session, journey_id, previous, updated, **kwargs):
        if self.drafts[previous.draft_id] != previous:
            raise AppError('VERSION_CONFLICT')
        self.drafts[previous.draft_id] = updated
        return updated

    async def cancel(self, *args):
        pass


async def main():
    app, _ = app_for_test()
    issued = await app.state.session_service.issue()
    id = uuid4()
    journeys = JourneyService(MemoryRolesStore(issued.session, id), app.state.consent_service, app.state.admission_service)
    await journeys.update_profile(issued.session, id, ready_edit())
    confirmation = await journeys.confirm_profile(issued.session, id, 2)
    with open_test_database("sqlite") as db:
        add = seeded(db)
        add(1, title="자료 정리", activity_district="seongdong", skill_tags=["자료 정리"],
            role_tags=["library_assistant"], requirements=[], source_checked_at=utc_now(), reviewed_at=utc_now())
        db.execute(insert(RoleDefinition), role(id="library_assistant", skill_tags=["자료 정리"]).model_dump())
        opportunities = PublicOpportunityService(SqlPublicOpportunityRepository(lambda: nullcontext(db)))
        roles = RoleService(journeys, SQLRoleCatalog(lambda: nullcontext(db)))
        app.state.recommendation_service = RecommendationService(journeys, opportunities, roles)
        app.state.eligibility_service = EligibilityService(journeys, opportunities)
        app.state.draft_service = DraftService(MemoryDraftStore(), journeys, opportunities, None)
        app.state.journey_service, app.state.role_service = journeys, roles
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://testserver") as client:
            client.cookies.set("__Host-rc_session", issued.token)
            await client.get("/api/v1/me")
            response = await client.post("/api/v1/recommendations", json={"profile": confirmation.profile.model_dump(mode="json"), "filters": {}}, headers=csrf(client))
            profile = await client.get(f"/api/v1/journeys/{id}/profile")
            role_candidates = await client.get(f"/api/v1/journeys/{id}/roles")
            exclusions = await client.get(f"/api/v1/journeys/{id}/role-exclusions")
            eligibility = await client.post('/api/v1/opportunities/00000000-0000-0000-0000-000000000001/eligibility',
                json={"profile": confirmation.profile.model_dump(mode="json"), "opportunity_version": 1}, headers=csrf(client))
            created = await client.post(f'/api/v1/journeys/{id}/drafts', headers={**csrf(client), 'Idempotency-Key': str(uuid4())},
                json={'mode': 'manual', 'profile_version': 1, 'opportunity': {'id': '00000000-0000-0000-0000-000000000001', 'version': 1}, 'saved_document': None})
            draft_path = f'/api/v1/journeys/{id}/drafts/{created.json()["draft_id"]}'
            edited = await client.patch(draft_path, headers=csrf(client), json={'self_introduction': '직접 쓴 가상 경험', 'motivation': '직접 쓴 가상 동기', 'base_revision': 1})
            approved = await client.post(draft_path + '/approve', headers=csrf(client), json={'base_revision': 2})
            displayed = await client.get(draft_path)
            print(json.dumps({"status": response.status_code, "body": response.json(),
                "profile": profile.json(), "roles": role_candidates.json(), "exclusions": exclusions.json(), "eligibility_status": eligibility.status_code, "eligibility": eligibility.json(),
                'draft_statuses': [created.status_code, edited.status_code, approved.status_code, displayed.status_code],
                'drafts': [item.json() for item in (created, edited, approved, displayed)]}, ensure_ascii=True))


asyncio.run(main())
