"""재확정 전후 불변 근거·파생 결과 갱신·지원서 표시 인터페이스 (SEC-02/TIM-01)."""

from contextlib import nullcontext
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import insert

from app.contracts.journey import ProfileRef, ProfileUpdate
from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.eligibility.service import EligibilityService
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import PublicOpportunityService
from app.modules.recommendations.service import RecommendationService
from app.modules.roles.repository import SQLRoleCatalog
from app.modules.roles.service import RoleService
from app.persistence.operations import RoleDefinition
from tests.persistence_helpers import open_test_database
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_journeys import BODY, real_services
from tests.test_profile_confirmation import ready_edit
from tests.test_public_opportunities import seeded
from tests.test_recommendation_filters import certification
from tests.test_roles import role


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_real_reconfirmation_invalidates_recommendations_eligibility_and_marks_old_draft_reference(backend):
    async def scenario(admission, admission_store, redis):
        issued, sessions, journeys, _, _, identity = await real_services(admission, admission_store, redis)
        journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
        edit = ready_edit().model_dump(mode="json")
        edit["draft"]["certifications"] = ["가상자격A"]
        await journeys.update_profile(issued.session, journey.journey_id, ProfileUpdate.model_validate(edit))
        confirmation = await journeys.confirm_profile(issued.session, journey.journey_id, 2)
        snapshot = await journeys.resolve_profile(issued.session, confirmation.profile)
        before = await journeys.profile_dependency(issued.session, confirmation.profile)
        assert before.reference == before.current_profile and before.review_reasons == ()
        with open_test_database(backend) as db:
            add = seeded(db)
            now = utc_now()
            target = add(1, title="자료 정리", activity_district="seongdong", skill_tags=["자료 정리"],
                role_tags=["library_assistant"], requirements=[certification("가상자격A")], source_checked_at=now, reviewed_at=now)
            db.execute(insert(RoleDefinition), role(id="library_assistant", skill_tags=["자료 정리"]).model_dump())
            opportunities = PublicOpportunityService(SqlPublicOpportunityRepository(lambda: nullcontext(db)))
            roles = RoleService(journeys, SQLRoleCatalog(lambda: nullcontext(db)))
            app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
            app.state.session_service, app.state.consent_service = sessions, journeys.consents
            app.state.admission_service = admission
            app.state.eligibility_service = EligibilityService(journeys, opportunities)
            app.state.recommendation_service = RecommendationService(journeys, opportunities, roles)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://testserver") as client:
                client.cookies.set("__Host-rc_session", issued.token)
                await client.get("/api/v1/me")
                reference = confirmation.profile.model_dump(mode="json")
                async def results(ref):
                    rec = await client.post("/api/v1/recommendations", json={"profile": ref, "filters": {}}, headers=csrf(client))
                    eligible = await client.post(f"/api/v1/opportunities/{target}/eligibility", json={"profile": ref, "opportunity_version": 1}, headers=csrf(client))
                    return rec, eligible
                rec, eligible = await results(reference)
                assert len(rec.json()["items"]) == 1 and eligible.json()["overall"] == "satisfied"
                draft = (await journeys.profile(issued.session, journey.journey_id)).draft.model_dump(mode="json")
                draft["certifications"] = []
                await journeys.update_profile(issued.session, journey.journey_id, ProfileUpdate.model_validate({"draft": draft, "base_revision": 3}))
                editing = await journeys.profile_dependency(issued.session, confirmation.profile)
                assert editing.review_reasons == () and editing.based_on_previous_confirmed
                rec, eligible = await results(reference)
                assert rec.json()["based_on_previous_confirmed"] and eligible.json()["overall"] == "satisfied"
                new = await journeys.confirm_profile(issued.session, journey.journey_id, 4)
                for response in await results(reference):
                    assert response.status_code == 409 and response.json()["code"] == "VERSION_CONFLICT"
                changed = await journeys.profile_dependency(issued.session, confirmation.profile)
                assert changed.reference == confirmation.profile and changed.current_profile == new.profile
                assert changed.review_reasons == ("profile_changed",) and not changed.based_on_previous_confirmed
                # 인터페이스는 이전 근거를 새 프로필로 덮어쓰거나 이전 내용을 바꾸지 않는다.
                assert (await journeys.resolve_profile(issued.session, changed.reference)).content == snapshot.content
                rec, eligible = await results(new.profile.model_dump(mode="json"))
                assert rec.json()["items"] == [] and eligible.json()["overall"] == "not_satisfied"
        for ref, actor, code in [
            (confirmation.profile, replace(issued.session, subject_id=uuid4()), "NOT_FOUND"),
            (ProfileRef(kind="journey", id=journey.journey_id, version=99), issued.session, "VERSION_CONFLICT"),
            (ProfileRef(kind="saved", id=journey.journey_id, version=1), issued.session, "UNAUTHENTICATED"),
        ]:
            with pytest.raises(AppError, match=code):
                await journeys.profile_dependency(actor, ref)
        resource = journeys.store.resource_key(issued.session.subject_id, journey.journey_id)
        await redis.delete(resource)
        with pytest.raises(AppError, match="NOT_FOUND"):
            await journeys.profile_dependency(issued.session, confirmation.profile)
    with_redis(scenario)
