"""W13-02 승인·버전·추천 경계 연결 시험 (SEC-02 부적절한 인가 / TIM-01 경쟁조건).

모듈별 시험은 경계를 하나씩 본다. 여기서는 실제 Redis 체험·확정본과 SQL 공개 공고를 한 HTTP 앱에 묶고
확정 → 추천·자격 → 공고 중요 변경·재검수 → 역할 제외·복원 → 재확정을 이어가며, 공고 변경이나 프로필 수정 뒤에
이전 사실로 판단하지 않는지 본다. 명세 시험 항목과의 대응: docs/data/boundary-tests.md
"""

from contextlib import contextmanager, nullcontext
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import insert

from app.contracts.journey import ProfileUpdate
from app.contracts.time import utc_now
from app.core.config import Settings
from app.main import create_app
from app.modules.eligibility.service import EligibilityService
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import PublicOpportunityService
from app.modules.opportunity_reviews.models import ReviewCommand
from app.modules.opportunity_reviews.repository import SqlOpportunityReviewRepository
from app.modules.opportunity_reviews.service import check_publishable
from app.modules.recommendations.service import RecommendationService
from app.modules.roles.repository import SQLRoleCatalog
from app.modules.roles.service import RoleService
from app.persistence import OpportunityVersion
from app.persistence.operations import RoleDefinition
from tests.persistence_helpers import open_test_database, opportunity_values
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_journeys import BODY, real_services
from tests.test_opportunity_reviews import OFFICIAL, REQUEST_ID
from tests.test_profile_confirmation import ready_edit
from tests.test_public_opportunities import seeded
from tests.test_recommendation_filters import certification
from tests.test_roles import role


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_confirmation_review_and_exclusion_boundaries_hold_across_one_journey(backend):
    async def scenario(admission, admission_store, redis):
        issued, sessions, journeys, _, _, identity = await real_services(admission, admission_store, redis)
        journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
        with open_test_database(backend) as db:
            add = seeded(db)
            now = utc_now()
            fresh = {"activity_district": "seongdong", "skill_tags": ["자료 정리"], "source_checked_at": now,
                     "reviewed_at": now, "source_url": OFFICIAL, "application_url": OFFICIAL}
            group = uuid4()
            either = add(1, title="자료 정리 A", role_tags=["library_assistant"], requirements=[
                certification("가상자격A", group=group), certification("가상자격B", group=group)], **fresh)
            missing = add(2, title="자료 정리 B", role_tags=["library_assistant"], requirements=[certification("가상자격C")], **fresh)
            unclear = add(3, title="자료 정리 C", role_tags=["library_assistant"],
                          requirements=[certification("가상자격A", clarity="needs_review")], **fresh)
            ended = add(4, title="자료 정리 D", role_tags=["library_assistant"], requirements=[],
                        **{**fresh, "deadline_date": (now - timedelta(days=2)).date()})
            reading = add(5, title="자료 정리 E", role_tags=["reading_companion"], requirements=[], **fresh)
            db.execute(insert(RoleDefinition), [
                role(id="library_assistant", name="가상 도서관 도우미", skill_tags=["자료 정리"]).model_dump(),
                role(id="reading_companion", skill_tags=["자료 정리"]).model_dump(),
            ])
            opportunities = PublicOpportunityService(SqlPublicOpportunityRepository(lambda: nullcontext(db)))
            roles = RoleService(journeys, SQLRoleCatalog(lambda: nullcontext(db)))
            app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
            app.state.session_service, app.state.consent_service = sessions, journeys.consents
            app.state.admission_service, app.state.opportunity_service, app.state.role_service = admission, opportunities, roles
            app.state.eligibility_service = EligibilityService(journeys, opportunities)
            app.state.recommendation_service = RecommendationService(journeys, opportunities, roles)

            @contextmanager
            def savepoint():
                with db.begin_nested():
                    yield db

            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://testserver") as client:
                client.cookies.set("__Host-rc_session", issued.token)
                await client.get("/api/v1/me")

                async def recommend(ref):
                    return await client.post("/api/v1/recommendations", json={"profile": ref, "filters": {}}, headers=csrf(client))

                async def eligibility(opportunity, ref, version):
                    return await client.post(f"/api/v1/opportunities/{opportunity}/eligibility",
                                             json={"profile": ref, "opportunity_version": version}, headers=csrf(client))

                def items(response):
                    assert response.status_code == 200, response.text
                    return {item["opportunity"]["id"]: item for item in response.json()["items"]}

                async def revision():
                    return (await journeys.profile(issued.session, journey.journey_id)).revision

                # 1. 초안·소유권·버전 거절: 확정 전 참조는 추천·자격 모두 받지 않는다.
                draft_ref = {"kind": "journey", "id": str(journey.journey_id), "version": 1}
                assert (await recommend(draft_ref)).json()["code"] == "PROFILE_NOT_CONFIRMED"
                assert (await eligibility(either, draft_ref, 1)).json()["code"] == "PROFILE_NOT_CONFIRMED"
                edit = ready_edit().model_dump(mode="json")
                edit["draft"]["certifications"] = ["가상자격A"]
                await journeys.update_profile(issued.session, journey.journey_id, ProfileUpdate.model_validate(edit))
                first = await journeys.confirm_profile(issued.session, journey.journey_id, await revision())
                first_ref = first.profile.model_dump(mode="json")
                snapshot = await journeys.resolve_profile(issued.session, first.profile)
                evidence = [str(snapshot.content.experiences[0].id)]

                # 2. OR 그룹 하나만 충족해도 유지, 필수 미충족·마감은 빠지고, 해석하지 못한 조건은 확인 필요로 남는다.
                found = items(await recommend(first_ref))
                assert set(found) == {str(either), str(unclear), str(reading)}
                assert found[str(either)]["eligibility"] == {"overall": "satisfied", "needs_review_count": 0, "no_requirements": False}
                assert found[str(unclear)]["eligibility"]["overall"] == "unknown"
                assert found[str(unclear)]["eligibility"]["needs_review_count"] == 1
                # 3. 모든 추천 근거는 확정본의 실제 경험이다.
                assert all(item["matched"]["experience_ids"] == evidence for item in found.values())
                assert (await eligibility(missing, first_ref, 1)).json()["overall"] == "not_satisfied"
                # 개인 추천에서 빠진 공고도 공개 검색에서는 사라지지 않는다. 마감 공고는 마감으로 보인다.
                assert (await client.get(f"/api/v1/opportunities/{ended}")).json()["recruitment_status"] == "closed"
                # 소유권·버전: 다른 주체는 존재를 알 수 없고, 없는 확정 버전은 충돌이다.
                stranger = await sessions.issue()
                outsider = httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://testserver")
                async with outsider:
                    outsider.cookies.set("__Host-rc_session", stranger.token)
                    await outsider.get("/api/v1/me")
                    for response in [
                        await outsider.post("/api/v1/recommendations", json={"profile": first_ref, "filters": {}}, headers=csrf(outsider)),
                        await outsider.post(f"/api/v1/opportunities/{either}/eligibility",
                                            json={"profile": first_ref, "opportunity_version": 1}, headers=csrf(outsider)),
                        await outsider.put(f"/api/v1/journeys/{journey.journey_id}/role-exclusions",
                                           json={"role_ids": ["reading_companion"], "base_revision": await revision()}, headers=csrf(outsider)),
                    ]:
                        assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
                assert (await recommend({**first_ref, "version": 99})).json()["code"] == "VERSION_CONFLICT"
                assert (await eligibility(either, first_ref, 2)).json()["code"] == "VERSION_CONFLICT"

                # 공고 중요 변경(OR 해제)이 수집되면 재검수 전까지 추천·지원서 준비 대상에서 빠진다.
                # 공개본은 그대로라 자격 판정은 공개 1판 기준이고, 신청 안내는 변경 대기를 알린다.
                db.execute(insert(OpportunityVersion), opportunity_values(either, 2, **{
                    **fresh, "title": "자료 정리 A", "role_tags": ["library_assistant"], "reviewed_at": None,
                    "requirements": [certification("가상자격B")]}))
                assert str(either) not in items(await recommend(first_ref))
                assert (await eligibility(either, first_ref, 1)).json()["overall"] == "satisfied"
                preparation = (await client.get(f"/api/v1/opportunities/{either}/preparation")).json()
                assert preparation["opportunity"]["version"] == 1 and preparation["change_pending"]
                assert preparation["application_url"] == OFFICIAL
                # 운영자가 새 판을 승인하면 이전 판 기준의 판정은 충돌이고, 새 판 기준으로 다시 판단한다.
                SqlOpportunityReviewRepository(savepoint).apply(either, ReviewCommand(
                    action="approve", base_version=2, reason_code=None, note="공식 원문 확인", actor_id=uuid4(),
                    request_id=REQUEST_ID, at=utc_now()), check_publishable)
                assert (await eligibility(either, first_ref, 1)).json()["code"] == "VERSION_CONFLICT"
                assert (await eligibility(either, first_ref, 2)).json()["overall"] == "not_satisfied"
                assert str(either) not in items(await recommend(first_ref))
                preparation = (await client.get(f"/api/v1/opportunities/{either}/preparation")).json()
                assert preparation["opportunity"]["version"] == 2 and not preparation["change_pending"]

                # 역할 제외는 그 역할이 붙은 공고만 개인 추천에서 빼고, 오래된 리비전 기준 변경은 받지 않는다.
                path = f"/api/v1/journeys/{journey.journey_id}/role-exclusions"
                base = await revision()
                excluded = await client.put(path, json={"role_ids": ["reading_companion"], "base_revision": base}, headers=csrf(client))
                assert excluded.status_code == 200 and excluded.json()["role_ids"] == ["reading_companion"]
                assert set(items(await recommend(first_ref))) == {str(unclear)}
                stale = await client.put(path, json={"role_ids": [], "base_revision": base}, headers=csrf(client))
                assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
                restored = await client.put(path, json={"role_ids": [], "base_revision": await revision()}, headers=csrf(client))
                assert restored.status_code == 200 and restored.json()["role_ids"] == []
                assert set(items(await recommend(first_ref))) == {str(unclear), str(reading)}

                # 재확정하면 이전 확정본 기준의 추천·자격은 충돌이고, 새 확정본으로 새 공고 판을 다시 판단한다.
                draft = (await journeys.profile(issued.session, journey.journey_id)).draft.model_dump(mode="json")
                draft["certifications"] = ["가상자격B"]
                await journeys.update_profile(issued.session, journey.journey_id,
                                              ProfileUpdate.model_validate({"draft": draft, "base_revision": await revision()}))
                second = await journeys.confirm_profile(issued.session, journey.journey_id, await revision())
                for response in (await recommend(first_ref), await eligibility(either, first_ref, 2)):
                    assert response.status_code == 409 and response.json()["code"] == "VERSION_CONFLICT"
                second_ref = second.profile.model_dump(mode="json")
                found = items(await recommend(second_ref))
                assert set(found) == {str(either), str(unclear), str(reading)}
                assert found[str(either)]["eligibility"]["overall"] == "satisfied"
                # 확정본 A만 근거였던 확인 필요 조건은 새 확정본에서도 단정하지 않는다.
                assert found[str(unclear)]["eligibility"]["overall"] == "unknown"
                assert (await eligibility(either, second_ref, 2)).json()["overall"] == "satisfied"
                # 이전 확정본 내용은 덮어쓰지 않는다.
                assert (await journeys.resolve_profile(issued.session, first.profile)).content == snapshot.content
    with_redis(scenario)
