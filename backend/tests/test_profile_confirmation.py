"""명시적 확정·불변 버전·근거 참조: 부적절한 인가(SEC-02), TOCTOU(TIM-01)."""

import asyncio
from dataclasses import replace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.contracts.journey import BaseRevision, ConfirmedVersion, ProfileConfirmResult, ProfileRef
from app.core.business_errors import AppError
from app.modules.journeys.repository import MAX_CONFIRMED_VERSIONS
from app.modules.journeys.service import JourneyService, MissingProfileFields, ResolvedJourneyProfile
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_journeys import NOW, BODY, app_for_test, real_services
from tests.test_manual_profile import MemoryProfileStore, edit_body


def ready_edit(revision=1, description="가상 도서관 경험"):
    body = edit_body(revision=revision).model_dump(mode="json")
    body["draft"]["preferred_regions"] = [{"province": "seoul", "district": "seongdong"}]
    body["draft"]["activity_types"] = ["volunteering"]
    body["draft"]["experiences"][0]["description"] = description
    return type(edit_body()).model_validate(body)


class MemoryConfirmedStore(MemoryProfileStore):
    """서비스/HTTP 확인용. 실제 원자성은 Redis 전용 시험에서 검증한다."""
    def __init__(self, session, journey_id):
        super().__init__(session, journey_id)
        self.snapshots = {}

    async def confirm_profile(self, session, journey_id, draft, base_revision):
        current = await self.profile(session, journey_id)
        if current.revision != base_revision:
            raise AppError("VERSION_CONFLICT")
        version = len(self.snapshots) + 1
        self.snapshots[version] = draft.model_copy(deep=True)
        confirmation = ConfirmedVersion(version=version, confirmed_at=NOW)
        self.view = current.model_copy(update={"confirmed": confirmation, "revision": current.revision + 1,
                                              "has_unconfirmed_changes": False})
        return ProfileConfirmResult(profile=ProfileRef(kind="journey", id=journey_id, version=version),
                                    confirmed_at=NOW, revision=self.view.revision)

    async def resolve_profile(self, session, reference, *, require_current=False):
        current = await self.profile(session, reference.id)
        if current.confirmed is None:
            raise AppError("PROFILE_NOT_CONFIRMED")
        if reference.version not in self.snapshots or require_current and reference.version != current.confirmed.version:
            raise AppError("VERSION_CONFLICT")
        return ResolvedJourneyProfile(reference, self.snapshots[reference.version].model_copy(deep=True), NOW)


async def services():
    app, _ = app_for_test()
    issued = await app.state.session_service.issue()
    journey = uuid4()
    store = MemoryConfirmedStore(issued.session, journey)
    service = JourneyService(store, app.state.consent_service, app.state.admission_service)
    return issued.session, journey, store, service


def test_missing_minimum_fields_never_confirm_and_unconfirmed_reference_is_rejected():
    async def scenario():
        session, journey, store, service = await services()
        with pytest.raises(MissingProfileFields) as caught:
            await service.confirm_profile(session, journey, 1)
        assert caught.value.fields == ("experiences", "preferred_regions", "activity_types")
        with pytest.raises(AppError, match="PROFILE_NOT_CONFIRMED"):
            await service.resolve_profile(session, ProfileRef(kind="journey", id=journey, version=1))
        assert store.snapshots == {} and store.view.revision == 1
    asyncio.run(scenario())


def test_confirmation_ref_is_server_owned_and_versions_survive_later_edit_and_reconfirmation():
    async def scenario():
        session, journey, _, service = await services()
        await service.update_profile(session, journey, ready_edit())
        first = await service.confirm_profile(session, journey, 2)
        assert first.profile == ProfileRef(kind="journey", id=journey, version=1)
        assert first.confirmed_at == NOW and first.revision == 3
        before = await service.resolve_profile(session, first.profile)
        await service.update_profile(session, journey, ready_edit(3, "사용자가 새로 수정한 경험"))
        assert (await service.profile(session, journey)).has_unconfirmed_changes is True
        assert (await service.resolve_profile(session, first.profile)).content == before.content
        second = await service.confirm_profile(session, journey, 4)
        assert second.profile.version == 2 and second.revision == 5
        assert (await service.resolve_profile(session, first.profile)).content == before.content
        assert not (await service.profile(session, journey)).has_unconfirmed_changes
        with pytest.raises(AppError, match="VERSION_CONFLICT"):
            await service.resolve_profile(session, first.profile, require_current=True)
        assert (await service.resolve_profile(session, second.profile, require_current=True)).reference == second.profile
    asyncio.run(scenario())


def test_stale_confirmation_other_subject_and_forged_saved_reference_cannot_resolve():
    async def scenario():
        session, journey, store, service = await services()
        await service.update_profile(session, journey, ready_edit())
        confirmed = await service.confirm_profile(session, journey, 2)
        with pytest.raises(AppError, match="VERSION_CONFLICT"):
            await service.confirm_profile(session, journey, 2)
        with pytest.raises(AppError, match="NOT_FOUND"):
            await service.resolve_profile(replace(session, subject_id=uuid4()), confirmed.profile)
        with pytest.raises(AppError, match="UNAUTHENTICATED"):
            await service.resolve_profile(session, confirmed.profile.model_copy(update={"kind": "saved"}))
        with pytest.raises(AppError, match="VERSION_CONFLICT"):
            await service.resolve_profile(session, confirmed.profile.model_copy(update={"version": 99}))
        assert len(store.snapshots) == 1
    asyncio.run(scenario())


def test_http_missing_fields_use_required_reasons_and_success_needs_explicit_csrf_request():
    app, _ = app_for_test()
    with TestClient(app, base_url="https://testserver", client=("192.0.2.1", 50000)) as client:
        client.get("/api/v1/me")
        session = next(iter(app.state.session_service.store.records.values()))
        journey = uuid4()
        store = MemoryConfirmedStore(session, journey)
        app.state.journey_service = JourneyService(store, app.state.consent_service, app.state.admission_service)
        url = f"/api/v1/journeys/{journey}/profile"
        missing = client.post(url + "/confirm", json={"base_revision": 1}, headers=csrf(client))
        assert missing.status_code == 422
        assert missing.json()["fields"] == [{"path": "draft." + name, "reason": "required"}
                                            for name in ("experiences", "preferred_regions", "activity_types")]
        assert client.patch(url, json=ready_edit().model_dump(mode="json"), headers=csrf(client)).status_code == 200
        assert client.post(url + "/confirm", json={"base_revision": 2}).status_code == 403
        confirmed = client.post(url + "/confirm", json={"base_revision": 2}, headers=csrf(client))
        assert confirmed.status_code == 200 and confirmed.headers["cache-control"] == "no-store"
        assert confirmed.json()["profile"] == {"kind": "journey", "id": str(journey), "version": 1}
        assert confirmed.json()["revision"] == 3
        assert client.get(url).json()["confirmed"] == {"version": 1, "confirmed_at": confirmed.json()["confirmed_at"]}
        attack = client.post(url + "/confirm", json={"base_revision": 3, "version": 99, "confirmed_at": "2099-01-01T00:00:00Z"}, headers=csrf(client))
        assert attack.status_code == 422 and len(store.snapshots) == 1


def test_confirmation_and_reference_contracts_forbid_fake_body_or_boolean_revisions():
    with pytest.raises(ValidationError):
        BaseRevision(base_revision=True)
    with pytest.raises(ValidationError):
        ProfileRef.model_validate({"kind": "journey", "id": str(uuid4()), "version": 1, "content": ready_edit().draft.model_dump()})


def test_real_redis_confirmed_snapshot_is_immutable_and_latest_resolution_is_explicit():
    async def scenario(admission, admission_store, client):
        issued, _, service, _, _, identity = await real_services(admission, admission_store, client)
        journey = await service.create(issued.session, identity, str(uuid4()), BODY)
        await service.update_profile(issued.session, journey.journey_id, ready_edit())
        first = await service.confirm_profile(issued.session, journey.journey_id, 2)
        original = await service.resolve_profile(issued.session, first.profile)
        await service.update_profile(issued.session, journey.journey_id, ready_edit(3, "수정 후의 가상 경험"))
        second = await service.confirm_profile(issued.session, journey.journey_id, 4)
        assert second.profile.version == 2
        assert (await service.resolve_profile(issued.session, first.profile)).content == original.content
        with pytest.raises(AppError, match="VERSION_CONFLICT"):
            await service.resolve_profile(issued.session, first.profile, require_current=True)
        live = await service.load(issued.session, journey.journey_id)
        assert live.view.confirmed.version == 2
        assert live.view.confirmed.confirmed_at == second.confirmed_at
    with_redis(scenario)


def test_real_redis_two_confirmations_same_revision_have_one_winner_and_server_time():
    async def scenario(admission, admission_store, client):
        issued, _, service, _, _, identity = await real_services(admission, admission_store, client)
        journey = await service.create(issued.session, identity, str(uuid4()), BODY)
        await service.update_profile(issued.session, journey.journey_id, ready_edit())
        async def attempt():
            try:
                return await service.confirm_profile(issued.session, journey.journey_id, 2)
            except AppError as error:
                return error.code
        results = await asyncio.gather(attempt(), attempt())
        assert results.count("VERSION_CONFLICT") == 1
        winner = next(item for item in results if isinstance(item, ProfileConfirmResult))
        assert winner.profile.version == 1 and winner.revision == 3
        seconds, _ = await client.time()
        assert abs(winner.confirmed_at.timestamp() - seconds) < 3
    with_redis(scenario)


def test_real_redis_delete_between_validation_and_confirmation_cannot_resurrect_snapshot():
    async def scenario(admission, admission_store, client):
        issued, _, service, store, requests, identity = await real_services(admission, admission_store, client)
        journey = await service.create(issued.session, identity, str(uuid4()), BODY)
        current = await service.update_profile(issued.session, journey.journey_id, ready_edit())
        await requests.delete_resource(identity.subject_id, journey.journey_id)
        with pytest.raises(AppError, match="NOT_FOUND"):
            await store.confirm_profile(issued.session, journey.journey_id, current.draft, 2)
        assert not await client.exists(requests.resource_key(identity.subject_id, journey.journey_id) + ":lifecycle")
    with_redis(scenario)


def test_real_redis_confirmed_versions_are_bounded_and_never_overwritten():
    async def scenario(admission, admission_store, client):
        issued, _, service, _, requests, identity = await real_services(admission, admission_store, client)
        journey = await service.create(issued.session, identity, str(uuid4()), BODY)
        await service.update_profile(issued.session, journey.journey_id, ready_edit())
        for index in range(MAX_CONFIRMED_VERSIONS):
            result = await service.confirm_profile(issued.session, journey.journey_id, 2 + index)
            assert result.profile.version == index + 1
        with pytest.raises(AppError, match="RATE_LIMITED"):
            await service.confirm_profile(issued.session, journey.journey_id, 2 + MAX_CONFIRMED_VERSIONS)
        meta = requests.resource_key(identity.subject_id, journey.journey_id) + ":lifecycle"
        assert await client.hexists(meta, "confirmed:1:content")
        assert not await client.hexists(meta, f"confirmed:{MAX_CONFIRMED_VERSIONS + 1}:content")
    with_redis(scenario)
