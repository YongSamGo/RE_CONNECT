"""확정본 소유권·현재 공개 버전·null/빈 배열/거주 값·재평가의 정상/공격 입력."""

import asyncio
from contextlib import nullcontext
from dataclasses import replace
from datetime import date
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import insert, update

from app.contracts.eligibility import EligibilityRequest
from app.contracts.journey import ProfileRef, ProfileUpdate
from app.contracts.requirement import Requirement
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.eligibility.service import EligibilityService
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import PublicOpportunity, PublicOpportunityService
from app.persistence import OpportunityPublication, OpportunityVersion
from tests.persistence_helpers import NOW, open_test_database, opportunity_values
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_contracts import opportunity
from tests.test_journeys import BODY, real_services
from tests.test_profile_confirmation import ready_edit, services
from tests.test_public_opportunities import seeded


def requirement(field, operator=None, value=None, **changes):
    return Requirement.model_validate({"id": str(uuid4()), "field": field, "operator": operator, "value": value,
        "group_id": None, "group_operator": None, "reference_date": None,
        "source_evidence": "가상 공식 원문의 자격 조건", "clarity": "needs_review" if field == "other" else "clear", **changes})


def public_opportunity(requirements, version=1):
    values = opportunity()
    values.update(requirements=[r.model_dump(mode="json") for r in requirements])
    return PublicOpportunity(**values, id=uuid4(), version=version, description_truncated=False,
                             source_checked_at=NOW, reviewed_at=NOW, change_pending=False)


class PublicStore:
    def __init__(self, item):
        self.item, self.calls = item, 0

    def get(self, opportunity_id):
        self.calls += 1
        if opportunity_id != self.item.id:
            raise AppError("NOT_FOUND")
        return self.item


async def setup_case(requirements, profile_changes=None):
    session, journey, store, journeys = await services()
    body = ready_edit().model_dump(mode="json")
    body["draft"].update(profile_changes or {})
    await journeys.update_profile(session, journey, ProfileUpdate.model_validate(body))
    confirmed = await journeys.confirm_profile(session, journey, 2)
    public = PublicStore(public_opportunity(requirements))
    service = EligibilityService(journeys, public)
    return session, confirmed, journeys, public, service


@pytest.mark.parametrize("certificates,result,reason", [(None, "unknown", "missing_profile_value"),
    ([], "not_satisfied", None), (["사회복지사 2급"], "unknown", "unclear_requirement"),
    (["사회복지사 1급"], "satisfied", None)])
def test_certification_user_value_preserves_unknown_empty_and_exact_name(certificates, result, reason):
    async def scenario():
        condition = requirement("certification", "has_all", ["사회복지사 1급"])
        session, confirmed, _, public, service = await setup_case([condition], {"certifications": certificates})
        response = await service.check(session, public.item.id, EligibilityRequest(profile=confirmed.profile, opportunity_version=1))
        assert response.overall == result
        assert response.conditions[0].user_value == certificates and response.conditions[0].review_reason == reason
        assert response.conditions[0].source_evidence == condition.source_evidence
    asyncio.run(scenario())


def test_preferred_region_is_never_used_as_residence_and_actual_region_is_an_object():
    async def scenario():
        condition = requirement("residence_region", "in", [{"province": "seoul", "district": "seongdong"}])
        residence = {"province": "gyeonggi", "district": "suwon"}
        session, confirmed, _, public, service = await setup_case([condition], {"residence_region": residence})
        response = await service.check(session, public.item.id, EligibilityRequest(profile=confirmed.profile, opportunity_version=1))
        assert response.overall == "not_satisfied"
        assert response.model_dump(mode="json")["conditions"][0]["user_value"] == residence
    asyncio.run(scenario())


def test_or_group_does_not_turn_one_miss_into_overall_failure_and_age_boundary_stays_unknown():
    async def scenario():
        group = uuid4()
        conditions = [requirement("certification", "has_any", ["자격 확인"], group_id=group, group_operator="or"),
                      requirement("weekday", "includes_any", [3], group_id=group, group_operator="or"),
                      requirement("age", "gte", 68, reference_date=date(2026, 10, 15))]
        session, confirmed, _, public, service = await setup_case(conditions, {"certifications": [], "available_weekdays": [1, 3], "birth_year": 1958})
        response = await service.check(session, public.item.id, EligibilityRequest(profile=confirmed.profile, opportunity_version=1))
        assert response.groups[0].result == "satisfied" and response.overall == "unknown"
        assert response.conditions[-1].review_reason == "age_boundary"
        assert response.conditions[-1].user_value == 1958
    asyncio.run(scenario())


def test_no_requirements_is_distinct_from_unparsed_requirements():
    async def scenario():
        session, confirmed, _, public, service = await setup_case([])
        request = EligibilityRequest(profile=confirmed.profile, opportunity_version=1)
        empty = await service.check(session, public.item.id, request)
        assert empty.no_requirements is True and empty.overall == "satisfied" and empty.conditions == []
        public.item = public.item.model_copy(update={"requirements": [requirement("other")]})
        unknown = await service.check(session, public.item.id, request)
        assert not unknown.no_requirements and unknown.overall == "unknown"
        assert unknown.conditions[0].review_reason == "unclear_requirement"
    asyncio.run(scenario())


def test_cross_owner_stale_opportunity_and_late_profile_change_do_not_return_old_results():
    async def scenario():
        session, confirmed, journeys, public, service = await setup_case([])
        request = EligibilityRequest(profile=confirmed.profile, opportunity_version=1)
        with pytest.raises(AppError, match="NOT_FOUND"):
            await service.check(replace(session, subject_id=uuid4()), public.item.id, request)
        assert public.calls == 0
        with pytest.raises(AppError, match="VERSION_CONFLICT"):
            await service.check(session, public.item.id, request.model_copy(update={"opportunity_version": 99}))
        class ExpiringResolver:
            calls = 0
            async def resolve_profile(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 2:
                    raise AppError("NOT_FOUND")
                return await journeys.resolve_profile(*args, **kwargs)
        with pytest.raises(AppError, match="NOT_FOUND"):
            await EligibilityService(ExpiringResolver(), public).check(session, public.item.id, request)
    asyncio.run(scenario())


def test_opportunity_change_during_evaluation_is_reported_as_version_conflict():
    async def scenario():
        session, confirmed, journeys, public, _ = await setup_case([])
        class ChangingPublic(PublicStore):
            def get(self, opportunity_id):
                item = super().get(opportunity_id)
                return item if self.calls == 1 else item.model_copy(update={"version": 2})
        with pytest.raises(AppError, match="VERSION_CONFLICT"):
            await EligibilityService(journeys, ChangingPublic(public.item)).check(
                session, public.item.id, EligibilityRequest(profile=confirmed.profile, opportunity_version=1))
    asyncio.run(scenario())


def test_request_rejects_raw_profile_and_forged_decisions():
    reference = ProfileRef(kind="journey", id=uuid4(), version=1)
    for changes in ({"profile": {**reference.model_dump(), "content": {}}}, {"overall": "satisfied"}, {"opportunity_version": True}):
        with pytest.raises(ValidationError):
            EligibilityRequest.model_validate({"profile": reference.model_dump(), "opportunity_version": 1, **changes})


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_real_http_resolves_redis_confirmation_and_sql_publication_and_reevaluates(backend):
    async def scenario(admission, admission_store, redis):
        issued, sessions, journeys, _, _, identity = await real_services(admission, admission_store, redis)
        journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
        await journeys.update_profile(issued.session, journey.journey_id, ready_edit())
        confirmed = await journeys.confirm_profile(issued.session, journey.journey_id, 2)
        condition = requirement("residence_region", "in", [{"province": "seoul", "district": "seongdong"}])
        with open_test_database(backend) as db:
            opportunity_id = seeded(db)(1, requirements=[condition.model_dump(mode="json")])
            opportunities = PublicOpportunityService(SqlPublicOpportunityRepository(lambda: nullcontext(db)))
            app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
            app.state.session_service, app.state.consent_service = sessions, journeys.consents
            app.state.admission_service = admission
            app.state.eligibility_service = EligibilityService(journeys, opportunities)
            transport = httpx.ASGITransport(app, client=("192.0.2.1", 50000))
            async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
                client.cookies.set("__Host-rc_session", issued.token)
                await client.get("/api/v1/me")
                path = f"/api/v1/opportunities/{opportunity_id}/eligibility"
                body = {"profile": confirmed.profile.model_dump(mode="json"), "opportunity_version": 1}
                assert (await client.post(path, json=body)).status_code == 403
                first = await client.post(path, json=body, headers=csrf(client))
                assert first.status_code == 200 and first.headers["cache-control"] == "no-store"
                assert first.json()["overall"] == "unknown"
                assert first.json()["conditions"][0]["user_value"] is None
                edit = ready_edit(3).model_dump(mode="json")
                edit["draft"]["residence_region"] = {"province": "seoul", "district": "seongdong"}
                await journeys.update_profile(issued.session, journey.journey_id, ProfileUpdate.model_validate(edit))
                assert (await client.post(path, json=body, headers=csrf(client))).json()["overall"] == "unknown"
                newer = await journeys.confirm_profile(issued.session, journey.journey_id, 4)
                assert (await client.post(path, json=body, headers=csrf(client))).status_code == 409
                body["profile"] = newer.profile.model_dump(mode="json")
                assert (await client.post(path, json=body, headers=csrf(client))).json()["overall"] == "satisfied"
                changed = requirement("residence_region", "in", [{"province": "gyeonggi", "district": "suwon"}])
                db.execute(insert(OpportunityVersion), opportunity_values(opportunity_id, 2, review_status="approved", reviewed_at=NOW,
                                                                          requirements=[changed.model_dump(mode="json")]))
                db.execute(update(OpportunityPublication).where(OpportunityPublication.opportunity_id == opportunity_id).values(version=2))
                assert (await client.post(path, json=body, headers=csrf(client))).status_code == 409
                body["opportunity_version"] = 2
                response = await client.post(path, json=body, headers=csrf(client))
                assert response.json()["overall"] == "not_satisfied"
                assert response.json()["conditions"][0]["user_value"] == edit["draft"]["residence_region"]
    with_redis(scenario)
