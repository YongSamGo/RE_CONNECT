"""부적절한 인가(SEC-02)·TOCTOU(TIM-01): 수동 프로필 ID·CAS·수명·미확정 경계."""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.contracts.journey import ConfirmedVersion, ProfileDraftView, ProfileUpdate
from app.contracts.profile import ProfileContentInput, empty_profile_content
from app.core.business_errors import AppError
from app.modules.journeys.service import JourneyService
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_journeys import NOW, BODY, app_for_test, real_services


def edit_body(*, revision=1, experiences=None):
    draft = empty_profile_content().model_dump(mode="json")
    draft["experiences"] = experiences if experiences is not None else [{
        "id": None, "description": "가상 도서 정리 경험", "skill_tags": ["자료 정리"], "duration_note": None,
    }]
    return ProfileUpdate(draft=ProfileContentInput.model_validate(draft), base_revision=revision)


class MemoryProfileStore:
    """HTTP와 순수 서비스 검증 전용. Redis CAS/TTL 증거는 별도 시험이다."""
    def __init__(self, session, journey_id):
        self.owner, self.journey_id = session.subject_id, journey_id
        self.calls = []
        self.view = ProfileDraftView(revision=1, draft=empty_profile_content(), evidence=[], confirmed=None,
                                     has_unconfirmed_changes=False, missing_for_recommendation=["experiences", "preferred_regions", "activity_types"])

    async def profile(self, session, journey_id):
        if session.subject_id != self.owner or journey_id != self.journey_id:
            raise AppError("NOT_FOUND")
        return self.view

    async def update_profile(self, session, journey_id, draft, base_revision):
        current = await self.profile(session, journey_id)
        if current.revision != base_revision:
            raise AppError("VERSION_CONFLICT")
        self.calls.append(draft)
        self.view = current.model_copy(update={"draft": draft, "revision": current.revision + 1,
                                              "evidence": [], "missing_for_recommendation": draft.missing_for_recommendation(),
                                              "has_unconfirmed_changes": current.confirmed is not None})
        return self.view


async def unit_services():
    app, _ = app_for_test()
    issued = await app.state.session_service.issue()
    journey_id = uuid4()
    store = MemoryProfileStore(issued.session, journey_id)
    service = JourneyService(store, app.state.consent_service, app.state.admission_service)
    return issued.session, journey_id, store, service


def test_manual_edit_without_ai_consent_assigns_server_ids_and_preserves_owned_ids():
    async def scenario():
        session, journey, store, service = await unit_services()
        first = await service.update_profile(session, journey, edit_body())
        assert first.revision == 2 and first.confirmed is None and first.evidence == []
        experience = first.draft.experiences[0]
        assert experience.id is not None and experience.description == "가상 도서 정리 경험"
        second = await service.update_profile(session, journey, edit_body(revision=2, experiences=[{
            **experience.model_dump(), "description": "직접 고친 경험",
        }]))
        assert second.draft.experiences[0].id == experience.id
        assert second.draft.experiences[0].description == "직접 고친 경험"
        deleted = await service.update_profile(session, journey, edit_body(revision=3, experiences=[]))
        assert deleted.draft.experiences == [] and "experiences" in deleted.missing_for_recommendation
        assert len(store.calls) == 3
    asyncio.run(scenario())


def test_foreign_and_duplicate_ids_and_stale_revision_are_rejected_before_write():
    async def scenario():
        session, journey, store, service = await unit_services()
        foreign = edit_body().draft.experiences[0].model_dump()
        foreign["id"] = uuid4()
        with pytest.raises(AppError, match="VALIDATION_FAILED"):
            await service.update_profile(session, journey, edit_body(experiences=[foreign]))
        first = await service.update_profile(session, journey, edit_body())
        owned = first.draft.experiences[0].model_dump()
        with pytest.raises(AppError, match="VALIDATION_FAILED"):
            await service.update_profile(session, journey, edit_body(revision=2, experiences=[owned, owned]))
        with pytest.raises(AppError, match="VERSION_CONFLICT"):
            await service.update_profile(session, journey, edit_body(revision=1))
        assert len(store.calls) == 1
    asyncio.run(scenario())


def test_edit_keeps_previous_confirmation_and_requires_reconfirmation():
    async def scenario():
        session, journey, store, service = await unit_services()
        store.view = store.view.model_copy(update={"confirmed": ConfirmedVersion(version=2, confirmed_at=NOW)})
        result = await service.update_profile(session, journey, edit_body())
        assert result.confirmed.version == 2 and result.confirmed.confirmed_at == NOW
        assert result.has_unconfirmed_changes is True
    asyncio.run(scenario())


def test_http_get_patch_without_ai_consent_and_cross_owner_404():
    app, _ = app_for_test()
    with TestClient(app, base_url="https://testserver", client=("192.0.2.1", 50000)) as client:
        client.get("/api/v1/me")
        session = next(iter(app.state.session_service.store.records.values()))
        journey_id = uuid4()
        store = MemoryProfileStore(session, journey_id)
        app.state.journey_service = JourneyService(store, app.state.consent_service, app.state.admission_service)
        url = f"/api/v1/journeys/{journey_id}/profile"
        initial = client.get(url)
        assert initial.status_code == 200 and initial.headers["cache-control"] == "no-store"
        assert initial.json()["draft"]["certifications"] is None
        updated = client.patch(url, json=edit_body().model_dump(mode="json"), headers=csrf(client))
        assert updated.status_code == 200 and updated.json()["revision"] == 2
        assert client.patch(url, json=edit_body().model_dump(mode="json"), headers=csrf(client)).status_code == 409
        assert client.patch(url, json=edit_body(revision=2).model_dump(mode="json")).status_code == 403
        with TestClient(app, base_url="https://testserver", client=("192.0.2.2", 50001)) as stranger:
            stranger.get("/api/v1/me")
            assert stranger.get(url).status_code == 404


@pytest.mark.parametrize("change", [{"owner_id": str(uuid4())}, {"confirmed": True}, {"base_revision": True}])
def test_request_cannot_inject_owner_approval_or_boolean_revision(change):
    with pytest.raises(ValidationError):
        ProfileUpdate.model_validate({**edit_body().model_dump(mode="json"), **change})


@pytest.mark.parametrize("field,value", [("available_weekdays", [0]), ("hours_per_week", -1),
                                         ("preferred_regions", [{"province": "seoul", "district": "suwon"}])])
def test_manual_profile_uses_existing_shared_field_and_region_validation(field, value):
    body = edit_body().model_dump(mode="json")
    body["draft"][field] = value
    with pytest.raises(ValidationError):
        ProfileUpdate.model_validate(body)


def test_real_redis_manual_edit_after_ai_consent_removed_and_polling_does_not_extend_ttl():
    async def scenario(admission, admission_store, client):
        issued, _, service, store, requests, identity = await real_services(admission, admission_store, client)
        journey = await service.create(issued.session, identity, str(uuid4()), BODY)
        session_key = store.session_key(issued.session.digest)
        await client.hdel(session_key, "ai_notice_version", "ai_granted_ms")
        resource = requests.resource_key(identity.subject_id, journey.journey_id)
        before = await client.pttl(resource)
        initial = await service.profile(issued.session, journey.journey_id)
        assert initial.draft == empty_profile_content()
        assert await client.pttl(resource) <= before
        updated = await service.update_profile(issued.session, journey.journey_id, edit_body())
        assert updated.revision == 2 and updated.draft.experiences[0].id is not None
        assert await client.hget(admission_store.control_key, "global") == "0"
        assert await client.hget(admission_store.control_key, "active") is None
    with_redis(scenario)


def test_real_redis_two_manual_edits_from_same_revision_have_one_winner():
    async def scenario(admission, admission_store, client):
        issued, _, service, _, _, identity = await real_services(admission, admission_store, client)
        journey = await service.create(issued.session, identity, str(uuid4()), BODY)
        async def attempt():
            try:
                await service.update_profile(issued.session, journey.journey_id, edit_body())
                return "ok"
            except AppError as error:
                return error.code
        results = await asyncio.gather(attempt(), attempt())
        assert sorted(results) == ["VERSION_CONFLICT", "ok"]
        assert (await service.profile(issued.session, journey.journey_id)).revision == 2
    with_redis(scenario)


def test_real_redis_delete_between_read_and_write_does_not_recreate_profile():
    async def scenario(admission, admission_store, client):
        issued, _, service, store, requests, identity = await real_services(admission, admission_store, client)
        journey = await service.create(issued.session, identity, str(uuid4()), BODY)
        await service.profile(issued.session, journey.journey_id)
        await requests.delete_resource(identity.subject_id, journey.journey_id)
        with pytest.raises(AppError, match="NOT_FOUND"):
            await store.update_profile(issued.session, journey.journey_id, empty_profile_content(), 1)
        assert not await client.exists(requests.resource_key(identity.subject_id, journey.journey_id))
    with_redis(scenario)
