"""명세 점수·근거 실재성·실제 DB/Redis HTTP·부적절한 인가(SEC-02)."""

import asyncio
from contextlib import nullcontext
from datetime import timedelta
from fractions import Fraction
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import insert

from app.contracts.journey import ProfileUpdate
from app.contracts.recommendation import RecommendationRequest
from app.contracts.time import utc_now
from app.core.config import Settings
from app.core.business_errors import AppError
from app.main import create_app
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import PublicOpportunityService
from app.modules.recommendations.filters import filter_candidates
from app.modules.recommendations.ranking import rank_candidates
from app.modules.recommendations.service import RecommendationService
from app.modules.roles.repository import SQLRoleCatalog
from app.modules.roles.service import RoleService
from app.persistence import OpportunityVersion
from app.persistence.operations import RoleDefinition
from tests.persistence_helpers import NOW, open_test_database
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_journeys import BODY, real_services
from tests.test_profile_confirmation import ready_edit
from tests.test_public_opportunities import seeded
from tests.test_recommendation_filters import profile, public
from tests.test_roles import role


def rank(person, items, catalog=None):
    from app.contracts.recommendation import RecommendationFilters
    return rank_candidates(person, filter_candidates(person, items, RecommendationFilters(), frozenset(), NOW), catalog or [])


def test_exact_jaccard_and_keyword_weights_use_sets_and_only_confirmed_facts():
    person = profile(skills=["자료 정리"])
    experience = person.experiences[0]
    # profile tags={자료 정리,낭독}, tokens={자료,정리,가상,낭독,경험}; 공고와 낭독 하나만 공유한다.
    item = public(title="낭독", description_text=None, skill_tags=["낭독"], role_tags=[])
    result = rank(person, [item])[0]
    assert result.score == Fraction(7, 10) * Fraction(1, 2) + Fraction(3, 10) * Fraction(1, 5)
    assert result.matched.experience_ids == [experience.id]
    assert result.matched.skill_tags == ["낭독"] and result.matched.keywords == []
    before = person.model_dump()
    assert rank(person, [item])[0].score == result.score and person.model_dump() == before


def test_zero_score_and_global_only_match_cannot_fabricate_experience_evidence():
    person = profile(skills=["독립역량"])
    assert rank(person, [public(title="무관한활동", description_text=None, skill_tags=[], role_tags=[])]) == []
    assert rank(person, [public(title="독립역량", description_text=None, skill_tags=["독립역량"], role_tags=[])]) == []


def test_aliases_match_only_reviewed_equivalence_and_preserve_original_tags():
    person = profile()
    value = person.model_dump()
    value["experiences"][0]["skill_tags"] = [" READING "]
    from app.contracts.profile import ProfileContent
    person = ProfileContent.model_validate(value)
    catalog = [role(aliases=[{"alias": "reading", "skill_tag": "낭독"}])]
    result = rank(person, [public(title="무관한활동", description_text=None, skill_tags=["낭독"], role_tags=["reading_companion"])], catalog)[0]
    assert result.matched.skill_tags == [" READING "] and result.matched.role_ids == ["reading_companion"]
    assert result.matched.experience_ids == [person.experiences[0].id]


def test_conflicting_cross_role_aliases_cannot_change_score_equivalence():
    catalog = [role(aliases=[{"alias": "shared", "skill_tag": "낭독"}]),
               role(id="other_role", skill_tags=["정리"], aliases=[{"alias": "shared", "skill_tag": "정리"}])]
    with pytest.raises(ValueError, match="별칭"):
        rank(profile(), [public()], catalog)


def test_tied_scores_order_kst_deadline_then_id_and_unknown_deadline_last_top_five():
    person = profile()
    common = {"title": "낭독", "description_text": None, "skill_tags": ["낭독"], "role_tags": []}
    items = [public(id=UUID(int=i), **common) for i in range(1, 8)]
    items[0] = public(id=UUID(int=1), deadline_date=(NOW + timedelta(days=1)).date(), **common)
    items[1] = public(id=UUID(int=2), deadline_at=NOW + timedelta(hours=16), **common)
    items[2] = public(id=UUID(int=3), deadline_at=NOW + timedelta(hours=16), **common)
    result = rank(person, list(reversed(items)))
    assert [item.candidate.opportunity.id.int for item in result] == [2, 3, 1, 4, 5]
    assert items[0].deadline_at is None


@pytest.mark.parametrize("word", ["업무", "마지막", "20년(관리소장", "가" * 60])
def test_free_text_overlap_cannot_create_experience_evidence(word):
    person = profile()
    value = person.model_dump()
    value["experiences"][0]["description"] = word
    value["experiences"][0]["skill_tags"] = []
    from app.contracts.profile import ProfileContent
    person = ProfileContent.model_validate(value)
    assert rank(person, [public(title=word, description_text=None, role_tags=[], skill_tags=[])]) == []


def test_free_text_only_ranks_supported_candidates_without_exposing_sentence_fragments():
    person = profile()
    value = person.model_dump()
    value["experiences"][0]["description"] = "업무 마지막 20년(관리소장"
    second = {**value["experiences"][0], "id": uuid4(), "skill_tags": ["무관한역량"]}
    value["experiences"].append(second)
    from app.contracts.profile import ProfileContent
    person = ProfileContent.model_validate(value)
    common = dict(description_text=None, skill_tags=["낭독"], role_tags=[])
    plain = rank(person, [public(title="낭독", **common)])[0]
    overlap = rank(person, [public(title="낭독 업무 마지막 20년(관리소장", **common)])[0]
    assert overlap.score > plain.score
    assert overlap.matched.experience_ids == [person.experiences[0].id]
    assert overlap.matched.keywords == [] and overlap.matched.skill_tags == ["낭독"]


@pytest.mark.parametrize("race", ["revision", "publication", "expired"])
def test_result_is_discarded_if_role_revision_publication_or_lifetime_changes(race):
    async def scenario():
        from app.modules.journeys.service import JourneyService
        from tests.test_journeys import app_for_test
        from tests.test_roles import MemoryRolesStore
        app, _ = app_for_test()
        session = (await app.state.session_service.issue()).session
        id = uuid4()
        store = MemoryRolesStore(session, id)
        journeys = JourneyService(store, app.state.consent_service, app.state.admission_service)
        await journeys.update_profile(session, id, ready_edit())
        confirmation = await journeys.confirm_profile(session, id, 2)
        item = public(title="자료 정리", skill_tags=["자료 정리"], activity_region={"province": "seoul", "district": "seongdong"}, source_checked_at=utc_now())
        class Opportunities:
            def recommendation_candidates(self, now):
                return [item]
            def get(self, id):
                return item.model_copy(update={"version": 2}) if race == "publication" else item
        class Roles:
            async def catalog_entries(self):
                if race == "revision":
                    store.view = store.view.model_copy(update={"revision": store.view.revision + 1})
                elif race == "expired":
                    async def expired(*args):
                        raise AppError("NOT_FOUND")
                    store.profile = expired
                return []
        service = RecommendationService(journeys, Opportunities(), Roles())
        with pytest.raises(AppError) as caught:
            await service.create(session, RecommendationRequest(profile=confirmation.profile, filters={}))
        assert caught.value.code in {"VERSION_CONFLICT", "NOT_FOUND"}
    asyncio.run(scenario())


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_real_http_recommendation_confirmed_snapshot_exclusions_unknown_and_version_checks(backend):
    async def scenario(admission, admission_store, redis):
        issued, sessions, journeys, _, _, identity = await real_services(admission, admission_store, redis)
        journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
        with open_test_database(backend) as db:
            add = seeded(db)
            now = utc_now()
            target = add(1, title="자료 정리", activity_district="seongdong", skill_tags=["자료 정리"],
                         role_tags=["library_assistant"], requirements=[], source_checked_at=now, reviewed_at=now)
            db.execute(insert(RoleDefinition), role(id="library_assistant", skill_tags=["자료 정리"]).model_dump())
            opportunities = PublicOpportunityService(SqlPublicOpportunityRepository(lambda: nullcontext(db)))
            roles = RoleService(journeys, SQLRoleCatalog(lambda: nullcontext(db)))
            app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
            app.state.session_service, app.state.consent_service = sessions, journeys.consents
            app.state.admission_service = admission
            app.state.recommendation_service = RecommendationService(journeys, opportunities, roles)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app, client=("192.0.2.1", 50000)), base_url="https://testserver") as client:
                client.cookies.set("__Host-rc_session", issued.token)
                await client.get("/api/v1/me")
                path = "/api/v1/recommendations"
                body = {"profile": {"kind": "journey", "id": str(journey.journey_id), "version": 1}, "filters": {}}
                assert (await client.post(path, json=body)).status_code == 403
                assert (await client.post(path, json=body, headers=csrf(client))).json()["code"] == "PROFILE_NOT_CONFIRMED"
                await journeys.update_profile(issued.session, journey.journey_id, ready_edit())
                confirmation = await journeys.confirm_profile(issued.session, journey.journey_id, 2)
                response = await client.post(path, json=body, headers=csrf(client))
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                data = response.json()
                assert len(data["items"]) == 1 and data["profile"] == body["profile"]
                item = data["items"][0]
                assert item["rank"] == 1 and item["opportunity"]["id"] == str(target)
                assert item["eligibility"] == {"overall": "satisfied", "needs_review_count": 0, "no_requirements": True}
                snapshot = await journeys.resolve_profile(issued.session, confirmation.profile)
                assert item["matched"]["experience_ids"] == [str(snapshot.content.experiences[0].id)]
                assert "score" not in item and not data["based_on_previous_confirmed"]
                # 검수된 알려진 자격이 없고 프로필 미확인일 때 unknown을 제거하지 않는다.
                from tests.test_recommendation_filters import certification
                db.execute(OpportunityVersion.__table__.update().where(OpportunityVersion.opportunity_id == target).values(
                    requirements=[certification("가상자격")]))
                data = (await client.post(path, json=body, headers=csrf(client))).json()
                assert data["items"][0]["eligibility"]["overall"] == "unknown"
                assert data["items"][0]["eligibility"]["needs_review_count"] == 1
                # 미확정 수정 중에도 마지막 확정본으로 계산하며 응답에 그 사실을 표시한다.
                draft = (await journeys.profile(issued.session, journey.journey_id)).draft.model_dump(mode="json")
                draft["skills"] = ["새 역량"]
                await journeys.update_profile(issued.session, journey.journey_id, ProfileUpdate.model_validate({"draft": draft, "base_revision": 3}))
                assert (await client.post(path, json=body, headers=csrf(client))).json()["based_on_previous_confirmed"]
                from app.contracts.roles import RoleExclusionUpdate
                await roles.set_exclusions(issued.session, journey.journey_id, RoleExclusionUpdate(role_ids=["library_assistant"], base_revision=4))
                assert (await client.post(path, json=body, headers=csrf(client))).json()["items"] == []
                await journeys.confirm_profile(issued.session, journey.journey_id, 5)
                assert (await client.post(path, json=body, headers=csrf(client))).status_code == 409
                stranger = await sessions.issue()
                client.cookies.clear()
                client.cookies.set("__Host-rc_session", stranger.token)
                await client.get("/api/v1/me")
                assert (await client.post(path, json=body, headers=csrf(client))).status_code == 404
    with_redis(scenario)
