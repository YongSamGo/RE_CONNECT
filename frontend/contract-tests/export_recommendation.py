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
from app.modules.roles.repository import SQLRoleCatalog  # noqa: E402
from app.modules.roles.service import RoleService  # noqa: E402
from app.persistence.operations import RoleDefinition  # noqa: E402
from tests.persistence_helpers import open_test_database  # noqa: E402
from tests.test_consents import csrf  # noqa: E402
from tests.test_profile_confirmation import ready_edit  # noqa: E402
from tests.test_public_opportunities import seeded  # noqa: E402


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
            print(json.dumps({"status": response.status_code, "body": response.json(),
                "profile": profile.json(), "roles": role_candidates.json(), "exclusions": exclusions.json(), "eligibility_status": eligibility.status_code, "eligibility": eligibility.json()}, ensure_ascii=True))


asyncio.run(main())
