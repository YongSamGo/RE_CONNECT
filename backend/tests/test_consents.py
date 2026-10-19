"""적절한 인증 없는 중요 기능 허용(SEC-01)·부적절한 인가(SEC-02)·CSRF(INP-11).

가상 주체/안내문으로 목적 분리·폐기/철회 버전 거절·정상 수락을 검사한다.
가짜 저장소 시험과 실제 Redis/PostgreSQL 시험을 구분한다.
"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, insert, select, update

from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.consents.models import ConsentCreate, ConsentState
from app.modules.consents.repository import RedisConsentStore, SQLConsentStore
from app.modules.consents.service import (
    ConsentActor, ConsentService, ConsentStoreUnavailable, ConsentSubjectExpired,
    ConsentVersionError,
)
from app.modules.sessions.service import SessionService
from app.persistence import Base, Consent, User
from tests.test_sessions import FakeStore, HttpAdmissionStub, with_redis

AI_VERSION = "ai-test-v1"
STORAGE_VERSION = "storage-test-v1"
NOW = datetime(2026, 10, 18, tzinfo=UTC)


class MemoryConsentStore:
    """HTTP 계약 확인용. Redis 원자성 검증을 대신하지 않는다."""
    def __init__(self):
        self.records = {}
        self.calls = []

    def key(self, actor, purpose):
        return (actor.member_id or actor.subject_id, purpose)

    async def grant(self, actor, request):
        self.calls.append((actor, request))
        key = self.key(actor, request.purpose)
        old = self.records.get(key)
        if old is not None and old.notice_version == request.notice_version:
            return old, False
        state = ConsentState(**request.model_dump(), granted_at=NOW)
        self.records[key] = state
        return state, True

    async def current(self, actor, purpose):
        return self.records.get(self.key(actor, purpose))


def service(store=None, **versions):
    return ConsentService(store or MemoryConsentStore(), ai_version=versions.get("ai_version", AI_VERSION),
                          storage_version=versions.get("storage_version", STORAGE_VERSION))


def grant(subject, purpose="ai_processing", version=AI_VERSION, handler=None):
    return asyncio.run((handler or service()).grant(subject, ConsentCreate(purpose=purpose, notice_version=version)))


def test_normal_acceptance_is_idempotent_and_purposes_are_separate():
    store = MemoryConsentStore()
    handler = service(store)
    actor = ConsentActor(uuid4(), member_id=uuid4())
    ai, created = grant(actor, handler=handler)
    assert created and ai.granted_at == NOW
    assert grant(actor, handler=handler) == (ai, False)
    with pytest.raises(AppError, match="CONSENT_REQUIRED"):
        asyncio.run(handler.require(actor, "storage"))
    storage, created = grant(actor, "storage", STORAGE_VERSION, handler)
    assert created and storage.purpose == "storage"
    assert asyncio.run(handler.require(actor, "storage")) == storage


def test_missing_discontinued_and_forged_notice_versions_never_authorize():
    actor = ConsentActor(uuid4())
    handler = service()
    with pytest.raises(AppError, match="CONSENT_REQUIRED"):
        asyncio.run(handler.require(actor, "ai_processing"))
    grant(actor, handler=handler)
    with pytest.raises(AppError, match="CONSENT_REQUIRED"):
        asyncio.run(handler.require(actor, "ai_processing", notice_version="retired"))
    changed = service(handler.store, ai_version="ai-test-v2")
    assert asyncio.run(changed.current(actor)) == []
    with pytest.raises(AppError, match="CONSENT_REQUIRED"):
        asyncio.run(changed.require(actor, "ai_processing"))
    with pytest.raises(ConsentVersionError):
        grant(actor, version="retired", handler=handler)
    assert len(handler.store.calls) == 1


def test_other_subject_and_anonymous_storage_cannot_use_an_existing_consent():
    handler = service()
    grant(ConsentActor(uuid4()), handler=handler)
    with pytest.raises(AppError, match="CONSENT_REQUIRED"):
        asyncio.run(handler.require(ConsentActor(uuid4()), "ai_processing"))
    with pytest.raises(AppError, match="UNAUTHENTICATED"):
        grant(ConsentActor(uuid4()), "storage", STORAGE_VERSION, handler)


def test_unconfigured_notices_do_not_silently_use_contract_example_versions():
    handler = service(ai_version=None, storage_version=None)
    actor = ConsentActor(uuid4())
    assert asyncio.run(handler.current(actor)) == []
    with pytest.raises(AppError, match="SERVICE_UNAVAILABLE"):
        grant(actor, handler=handler)
    with pytest.raises(AppError, match="CONSENT_REQUIRED"):
        asyncio.run(handler.require(actor, "ai_processing"))
    assert handler.store.calls == []


@pytest.mark.parametrize("exception,expected", [(ConsentStoreUnavailable, "SERVICE_UNAVAILABLE"), (ConsentSubjectExpired, "NOT_FOUND")])
def test_store_errors_fail_closed(exception, expected):
    class BrokenStore(MemoryConsentStore):
        async def grant(self, *args):
            raise exception

        current = grant

    handler = service(BrokenStore())
    actor = ConsentActor(uuid4())
    with pytest.raises(AppError, match=expected):
        grant(actor, handler=handler)
    with pytest.raises(AppError, match=expected):
        asyncio.run(handler.require(actor, "ai_processing"))


@pytest.mark.parametrize("value", ["", "a" * 33, "ＡＩ", "ai v1", "ai\n", "ai\u200bv1", 12, True])
def test_notice_versions_are_strict_ascii_and_bounded(value):
    with pytest.raises(ValidationError):
        ConsentCreate(purpose="ai_processing", notice_version=value)


def test_input_cannot_supply_owner_time_or_approval():
    for name in ("owner_id", "member_id", "granted_at", "accepted", "approved"):
        with pytest.raises(ValidationError):
            ConsentCreate.model_validate({"purpose": "ai_processing", "notice_version": AI_VERSION, name: "forged"})
    with pytest.raises(ValidationError):
        ConsentState(purpose="ai_processing", notice_version=AI_VERSION, granted_at=datetime(2026, 1, 1))


def http_app():
    app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver",
                              ai_notice_version=AI_VERSION, storage_notice_version=STORAGE_VERSION))
    app.state.session_service = SessionService(FakeStore())
    app.state.admission_service = HttpAdmissionStub()
    store = MemoryConsentStore()
    app.state.consent_service = service(store)
    return app, store


def csrf(client):
    return {"Origin": "https://testserver", "X-CSRF-Token": client.cookies.get("__Host-rc_csrf")}


def test_http_create_repeat_and_me_filter_current_notice():
    app, store = http_app()
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/api/v1/me").json()["consents"] == []
        payload = {"purpose": "ai_processing", "notice_version": AI_VERSION}
        response = client.post("/api/v1/consents", json=payload, headers=csrf(client))
        assert response.status_code == 201
        assert response.headers["cache-control"] == "no-store"
        assert set(response.json()) == {"purpose", "notice_version", "granted_at"}
        again = client.post("/api/v1/consents", json=payload, headers=csrf(client))
        assert again.status_code == 200 and again.json() == response.json()
        assert client.get("/api/v1/me").json()["consents"] == [response.json()]
        app.state.consent_service = service(store, ai_version="ai-test-v2")
        assert client.get("/api/v1/me").json()["consents"] == []


def test_http_stale_version_owner_injection_and_anonymous_storage_are_rejected(caplog):
    app, store = http_app()
    with TestClient(app, base_url="https://testserver") as client:
        client.get("/api/v1/me")
        payload = {"purpose": "ai_processing", "notice_version": "retired-version"}
        old = client.post("/api/v1/consents", json=payload, headers=csrf(client))
        assert old.status_code == 422
        assert old.json()["fields"] == [{"path": "notice_version", "reason": "invalid_value"}]
        assert "retired-version" not in old.text
        attack = {"purpose": "ai_processing", "notice_version": AI_VERSION, "member_id": str(uuid4())}
        assert client.post("/api/v1/consents", json=attack, headers=csrf(client)).status_code == 422
        storage = {"purpose": "storage", "notice_version": STORAGE_VERSION}
        response = client.post("/api/v1/consents?authenticated=true", json=storage,
                               headers={**csrf(client), "X-Member-ID": str(uuid4())})
        assert response.status_code == 401 and response.json()["code"] == "UNAUTHENTICATED"
        assert store.calls == []
        assert "retired-version" not in caplog.text


def test_http_csrf_fails_before_recording_consent():
    app, store = http_app()
    with TestClient(app, base_url="https://testserver") as client:
        client.get("/api/v1/me")
        payload = {"purpose": "ai_processing", "notice_version": AI_VERSION}
        assert client.post("/api/v1/consents", json=payload).status_code == 403
        headers = {**csrf(client), "Origin": "https://attacker.example"}
        assert client.post("/api/v1/consents", json=payload, headers=headers).status_code == 403
        assert store.calls == []


@pytest.fixture
def sql_store(tmp_path):
    # 파일 SQLite는 to_thread의 별도 접속에서도 같은 테스트 DB를 쓴다.
    engine = create_engine("sqlite:///" + str(tmp_path / "consents.db"))
    Base.metadata.create_all(engine)
    first, second, suspended = uuid4(), uuid4(), uuid4()
    with engine.begin() as db:
        db.execute(insert(User), [
            {"id": first, "kakao_subject": "fictional-consent-one", "status": "active"},
            {"id": second, "kakao_subject": "fictional-consent-two", "status": "active"},
            {"id": suspended, "kakao_subject": "fictional-consent-three", "status": "suspended"},
        ])
    yield SQLConsentStore(engine), first, second, suspended
    engine.dispose()


def test_sql_member_acceptance_is_idempotent_and_subject_scoped(sql_store):
    store, owner, other, suspended = sql_store
    handler = service(store)
    actor = ConsentActor(uuid4(), member_id=owner)
    first, created = grant(actor, "storage", STORAGE_VERSION, handler)
    assert created
    assert grant(actor, "storage", STORAGE_VERSION, handler) == (first, False)
    assert asyncio.run(handler.require(actor, "storage")) == first
    with pytest.raises(AppError, match="CONSENT_REQUIRED"):
        asyncio.run(handler.require(replace(actor, member_id=other), "storage"))
    for invalid in (suspended, uuid4()):
        with pytest.raises(AppError, match="NOT_FOUND"):
            grant(replace(actor, member_id=invalid), "storage", STORAGE_VERSION, handler)
    with store.engine.connect() as db:
        assert len(db.execute(select(Consent)).all()) == 1


def test_sql_withdrawal_does_not_resurrect_older_unwithdrawn_consent(sql_store):
    store, owner, _, _ = sql_store
    actor = ConsentActor(uuid4(), member_id=owner)
    with store.engine.begin() as db:
        db.execute(insert(Consent), [
            {"owner_id": owner, "purpose": "storage", "notice_version": STORAGE_VERSION,
             "accepted_at": NOW - timedelta(days=2), "withdrawn_at": None},
            {"owner_id": owner, "purpose": "storage", "notice_version": STORAGE_VERSION,
             "accepted_at": NOW - timedelta(days=1), "withdrawn_at": NOW},
        ])
    with pytest.raises(AppError, match="CONSENT_REQUIRED"):
        asyncio.run(service(store).require(actor, "storage"))


def test_sql_suspension_after_consent_blocks_further_use(sql_store):
    store, owner, _, _ = sql_store
    actor = ConsentActor(uuid4(), member_id=owner)
    handler = service(store)
    grant(actor, "storage", STORAGE_VERSION, handler)
    with store.engine.begin() as db:
        db.execute(update(User).where(User.id == owner).values(status="suspended"))
    with pytest.raises(AppError, match="NOT_FOUND"):
        asyncio.run(handler.require(actor, "storage"))


def test_real_redis_consent_idempotency_ttl_subject_and_revocation():
    async def scenario(sessions, sessions_store, client):
        issued = await sessions.issue()
        actor = ConsentActor(issued.session.subject_id, session_digest=issued.session.digest)
        store = RedisConsentStore(client, session_key=sessions_store.key)
        handler = service(store)
        key = sessions_store.key(issued.session.digest)
        before = await client.pttl(key)
        payload = ConsentCreate(purpose="ai_processing", notice_version=AI_VERSION)
        first, created = await handler.grant(actor, payload)
        assert created
        assert await handler.grant(actor, payload) == (first, False)
        assert await handler.require(actor, "ai_processing") == first
        assert 0 < await client.pttl(key) <= before
        with pytest.raises(AppError, match="NOT_FOUND"):
            await handler.require(replace(actor, subject_id=uuid4()), "ai_processing")
        await sessions.revoke(issued.token)
        with pytest.raises(AppError, match="NOT_FOUND"):
            await handler.grant(actor, payload)
        assert not await client.exists(key)

    with_redis(scenario)


def test_real_redis_expiry_during_grant_does_not_recreate_session():
    async def scenario(sessions, sessions_store, client):
        issued = await sessions.issue()
        actor = ConsentActor(issued.session.subject_id, session_digest=issued.session.digest)
        store = RedisConsentStore(client, session_key=sessions_store.key)
        key = sessions_store.key(issued.session.digest)
        # 임의로 만료된 해시가 남아 있는 상황도 서버 시간으로 재검사한다.
        await client.hset(key, mapping={"created_ms": 0, "last_ms": 0})
        with pytest.raises(AppError, match="NOT_FOUND"):
            await service(store).grant(actor, ConsentCreate(purpose="ai_processing", notice_version=AI_VERSION))
        assert not await client.exists(key)

    with_redis(scenario)
