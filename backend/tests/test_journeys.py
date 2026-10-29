"""동의/소유권/위조 요청과 체험 생성·수명. 가짜 HTTP 시험과 실제 Redis 시험을 분리한다."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.contracts.journey import Journey, JourneyCreate, Message
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.admission.service import AdmissionService, InferenceIdentity
from app.modules.consents.models import ConsentCreate
from app.modules.consents.repository import RedisConsentStore
from app.modules.consents.service import ConsentActor, ConsentService
from app.modules.journeys.repository import RedisJourneyStore
from app.modules.generation.questions import FIRST_QUESTION
from app.modules.journeys.service import JourneyRecord, JourneyService
from app.modules.requests.repository import RedisRequestStore
from app.modules.requests.service import CompletionGuard, RequestScope, RequestService, ResultReference, RESOURCE_MAX_MS
from app.modules.sessions.repository import RedisSessionStore
from app.modules.sessions.service import IDLE_MS, SessionService
from tests.test_admission import with_redis
from tests.test_consents import MemoryConsentStore, AI_VERSION, STORAGE_VERSION, csrf
from tests.test_sessions import FakeStore

NOW = datetime(2026, 10, 18, tzinfo=UTC)
BODY = JourneyCreate(ai_notice_version=AI_VERSION, saved_profile=None)


class MemoryJourneyStore:
    """HTTP 계약·거절 순서 전용. Lua/TTL/쿼터의 증거로 사용하지 않는다."""
    def __init__(self):
        self.records, self.calls = {}, []

    async def create(self, session, key_id, fingerprint, notice_version, budget, key_id_digest):
        self.calls.append((session, key_id, budget))
        key = (session.subject_id, key_id)
        if key not in self.records:
            view = Journey(journey_id=uuid4(), revision=1, expires_at=NOW + timedelta(hours=2),
                           idle_expires_at=NOW + timedelta(minutes=30),
                           first_message=Message(message_id=uuid4(), text=FIRST_QUESTION, created_at=NOW), confirmed=None)
            self.records[key] = JourneyRecord(view, CompletionGuard(session.digest, uuid4(), notice_version))
        return self.records[key]


class HttpLimitStore:
    async def check_http(self, identities, member):
        return None


def app_for_test():
    app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver",
                              ai_notice_version=AI_VERSION, storage_notice_version=STORAGE_VERSION))
    app.state.session_service = SessionService(FakeStore())
    app.state.admission_service = AdmissionService(HttpLimitStore(), identity_key=bytes(range(32)))
    app.state.consent_service = ConsentService(MemoryConsentStore(), ai_version=AI_VERSION, storage_version=STORAGE_VERSION)
    store = MemoryJourneyStore()
    app.state.journey_service = JourneyService(store, app.state.consent_service, app.state.admission_service)
    return app, store


def accept(client):
    client.get("/api/v1/me")
    response = client.post("/api/v1/consents", json={"purpose": "ai_processing", "notice_version": AI_VERSION}, headers=csrf(client))
    assert response.status_code == 201


def test_http_creation_and_repeat_keep_server_ids_question_and_lifetimes_without_ai():
    app, store = app_for_test()
    with TestClient(app, base_url="https://testserver", client=("192.0.2.1", 50000)) as client:
        accept(client)
        headers = {**csrf(client), "Idempotency-Key": str(uuid4()), "X-Forwarded-For": "198.51.100.1"}
        first = client.post("/api/v1/journeys", json=BODY.model_dump(), headers=headers)
        assert first.status_code == 201 and first.headers["cache-control"] == "no-store"
        parsed = Journey.model_validate(first.json())
        assert parsed.revision == 1 and parsed.confirmed is None
        assert parsed.first_message.text == FIRST_QUESTION
        assert parsed.expires_at - parsed.first_message.created_at == timedelta(hours=2)
        assert parsed.idle_expires_at - parsed.first_message.created_at == timedelta(minutes=30)
        assert client.post("/api/v1/journeys", json=BODY.model_dump(), headers=headers).json() == first.json()
        assert len(store.records) == 1
        assert store.calls[0][2] == app.state.admission_service.digest("generation-ip", "192.0.2.1")
        assert "subject_id" not in first.text and "session_digest" not in first.text


def test_no_consent_stale_version_and_csrf_never_reach_journey_store():
    app, store = app_for_test()
    with TestClient(app, base_url="https://testserver", client=("192.0.2.1", 50000)) as client:
        client.get("/api/v1/me")
        headers = {**csrf(client), "Idempotency-Key": str(uuid4())}
        assert client.post("/api/v1/journeys", json=BODY.model_dump(), headers=headers).json()["code"] == "CONSENT_REQUIRED"
        client.post("/api/v1/consents", json={"purpose": "ai_processing", "notice_version": AI_VERSION}, headers=csrf(client))
        assert client.post("/api/v1/journeys", json=BODY.model_dump(), headers={"Idempotency-Key": str(uuid4())}).status_code == 403
        assert client.post("/api/v1/journeys", json={**BODY.model_dump(), "ai_notice_version": "retired"}, headers=headers).status_code == 403
        assert store.calls == []


@pytest.mark.parametrize("change", [{"saved_profile": {"profile_id": str(uuid4()), "version": 1}},
                                    {"owner_id": str(uuid4())}, {"confirmed": True}, {"revision": 99}])
def test_saved_profile_and_authority_injection_cannot_create_an_anonymous_journey(change):
    app, store = app_for_test()
    with TestClient(app, base_url="https://testserver", client=("192.0.2.1", 50000)) as client:
        accept(client)
        response = client.post("/api/v1/journeys", json={**BODY.model_dump(), **change},
                               headers={**csrf(client), "Idempotency-Key": str(uuid4()), "X-Member-ID": str(uuid4())})
        assert response.status_code == (401 if "saved_profile" in change else 422)
        assert store.calls == []


@pytest.mark.parametrize("key", [None, "bad-key", uuid4().hex])
def test_invalid_idempotency_key_is_rejected_before_creation(key):
    app, store = app_for_test()
    with TestClient(app, base_url="https://testserver", client=("192.0.2.1", 50000)) as client:
        accept(client)
        response = client.post("/api/v1/journeys", json=BODY.model_dump(),
                               headers={**csrf(client), **({"Idempotency-Key": key} if key is not None else {})})
        assert response.status_code == 422 and store.calls == []


async def real_services(admission, admission_store, client):
    session_store = RedisSessionStore(client, prefix=admission_store.prefix + "sessions:")
    sessions = SessionService(session_store)
    issued = await sessions.issue()
    consents = ConsentService(RedisConsentStore(client, session_key=session_store.key), ai_version=AI_VERSION, storage_version=STORAGE_VERSION)
    await consents.grant(ConsentActor(issued.session.subject_id, session_digest=issued.session.digest), ConsentCreate(purpose="ai_processing", notice_version=AI_VERSION))
    request_store = RedisRequestStore(client, prefix=admission_store.prefix + "requests:", session_key=session_store.key)
    store = RedisJourneyStore(client, session_key=session_store.key, resource_key=request_store.resource_key,
                              control_key=admission_store.control_key, epoch=admission_store.epoch, prefix=admission_store.prefix + "journeys:")
    service = JourneyService(store, consents, admission)
    identity = InferenceIdentity(issued.session.subject_id, "192.0.2.1")
    return issued, sessions, service, store, request_store, identity


def test_real_redis_creation_replay_quota_and_guarded_request_completion():
    async def scenario(admission, admission_store, client):
        issued, _, service, _, requests, identity = await real_services(admission, admission_store, client)
        key = str(uuid4())
        journey = await service.create(issued.session, identity, key, BODY)
        assert await service.create(issued.session, identity, key, BODY) == journey
        assert await client.hget(admission_store.control_key, "limit:" + admission.generation_budget(identity)) == "1"
        assert await client.hget(admission_store.control_key, "global") == "0"  # 초기 질문은 실제 추론이 아니다.
        record = await service.load(issued.session, journey.journey_id)
        request_service = RequestService(requests)
        permit = await request_service.begin(RequestScope(identity.subject_id, "messages", journey.journey_id), str(uuid4()), {}, base_revision=1)
        await request_service.complete(permit, ResultReference("message", uuid4(), 2), guard=record.guard)
        assert (await service.load(issued.session, journey.journey_id)).view.revision == 2
    with_redis(scenario)


def test_real_redis_polling_does_not_touch_but_activity_is_capped_by_absolute_lifetime():
    async def scenario(admission, admission_store, client):
        issued, _, service, _, requests, identity = await real_services(admission, admission_store, client)
        journey = await service.create(issued.session, identity, str(uuid4()), BODY)
        resource = requests.resource_key(identity.subject_id, journey.journey_id)
        await client.pexpire(resource, 90000)
        await client.pexpire(resource + ":lifecycle", 90000)
        before = await client.pttl(resource)
        assert (await service.load(issued.session, journey.journey_id)).view == journey
        assert await client.pttl(resource) <= before
        seconds, micros = await client.time()
        now = seconds * 1000 + micros // 1000
        created = now - RESOURCE_MAX_MS + 10000
        await client.hset(resource + ":lifecycle", mapping={"created_ms": created, "last_ms": now - 1000})
        record = await service.load(issued.session, journey.journey_id, user_activity=True)
        assert 0 < await client.pttl(resource) <= 10000
        assert record.view.expires_at == datetime.fromtimestamp((created + RESOURCE_MAX_MS) / 1000, UTC)
        assert record.view.idle_expires_at == record.view.expires_at
    with_redis(scenario)


def test_real_redis_stt_and_creation_share_budget_and_repeat_is_free():
    async def scenario(admission, admission_store, client):
        issued, _, service, _, _, identity = await real_services(admission, admission_store, client)
        key = str(uuid4())
        await service.create(issued.session, identity, key, BODY)
        for _ in range(58):
            await service.create(issued.session, identity, str(uuid4()), BODY)
        async def ended(completion):
            completion.confirm_ended()
        await admission.run(identity, "stt", ended)
        with pytest.raises(AppError, match="DAILY_QUOTA_EXCEEDED"):
            await service.create(issued.session, identity, str(uuid4()), BODY)
        await service.create(issued.session, identity, key, BODY)
        assert await client.hget(admission_store.control_key, "global") == "1"
    with_redis(scenario)


def test_real_redis_80_concurrent_creations_have_exactly_60_winners():
    async def scenario(admission, admission_store, client):
        issued, _, service, _, _, identity = await real_services(admission, admission_store, client)
        async def attempt():
            try:
                await service.create(issued.session, identity, str(uuid4()), BODY)
                return "ok"
            except AppError as error:
                return error.code
        results = await asyncio.gather(*(attempt() for _ in range(80)))
        assert results.count("ok") == 60 and results.count("DAILY_QUOTA_EXCEEDED") == 20
    with_redis(scenario)


def test_real_redis_expired_or_deleted_journey_is_not_recreated_by_old_key():
    async def scenario(admission, admission_store, client):
        issued, _, service, _, requests, identity = await real_services(admission, admission_store, client)
        key = str(uuid4())
        journey = await service.create(issued.session, identity, key, BODY)
        await requests.delete_resource(identity.subject_id, journey.journey_id)
        with pytest.raises(AppError, match="NOT_FOUND"):
            await service.create(issued.session, identity, key, BODY)
        assert await client.hget(admission_store.control_key, "limit:" + admission.generation_budget(identity)) == "1"
        assert not await client.exists(requests.resource_key(identity.subject_id, journey.journey_id))
    with_redis(scenario)


def test_real_redis_cross_owner_and_session_revocation_block_load_and_creation():
    async def scenario(admission, admission_store, client):
        issued, sessions, service, store, _, identity = await real_services(admission, admission_store, client)
        journey = await service.create(issued.session, identity, str(uuid4()), BODY)
        stranger = replace(issued.session, subject_id=uuid4())
        with pytest.raises(AppError, match="NOT_FOUND"):
            await store.load(stranger, journey.journey_id, AI_VERSION, user_activity=False)
        await sessions.revoke(issued.token)
        with pytest.raises(AppError, match="NOT_FOUND"):
            await store.create(issued.session, uuid4(), "a" * 64, AI_VERSION,
                               admission.generation_budget(identity), admission.identity_key_id)
    with_redis(scenario)
