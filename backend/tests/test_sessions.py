"""실제 Redis 원자성/수명과 HTTP 쿠키·소유권 거절을 검증한다."""

import asyncio
import os
from uuid import UUID, uuid4

from fastapi import Request
from fastapi.testclient import TestClient
import pytest

from app.adapters.redis import build_redis
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.sessions.http import require_session
from app.modules.sessions.repository import RedisSessionStore
from app.modules.sessions.service import ABSOLUTE_MS, IDLE_MS, IssuedSession, Session, SessionService, StoreUnavailable, csrf_token, require_owner, token_digest, valid_csrf_cookie


class FakeStore:
    """HTTP 입출력 시험만 위한 저장소. TTL/원자성 판정에는 사용하지 않는다."""
    def __init__(self):
        self.records = {}

    async def create(self, digest, subject_id, secret):
        self.records[digest] = Session(subject_id, 1000, 1000, 1000, secret, digest)
        return self.records[digest]

    async def load(self, digest, *, touch):
        return self.records.get(digest)


def app_and_store(env="test"):
    app = create_app(Settings(_env_file=None, app_env=env))
    store = FakeStore()
    app.state.session_service = SessionService(store)
    resources = {}

    @app.get("/private/{resource_id}")
    async def private(resource_id: UUID, request: Request):
        session = await require_session(request)
        require_owner(session, resources.get(resource_id))
        return {"ok": True}

    return app, store, resources


def test_bootstrap_secure_cookies_contract_and_no_credentials_in_body():
    app, store, _ = app_and_store()
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/v1/me")
        assert response.json() == {"authenticated": False, "user": None, "consents": [], "pending_save_intent": None}
        assert response.headers["cache-control"] == "no-store"
        cookies = response.headers.get_list("set-cookie")
        session_cookie = next(item for item in cookies if item.startswith("__Host-rc_session="))
        csrf_cookie = next(item for item in cookies if item.startswith("__Host-rc_csrf="))
        assert all(value in session_cookie for value in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"))
        assert all(value in csrf_cookie for value in ("Secure", "SameSite=strict", "Path=/"))
        assert "Domain=" not in session_cookie and "HttpOnly" not in csrf_cookie
        token = client.cookies.get("__Host-rc_session")
        session = store.records[token_digest(token)]
        assert token not in response.text and session.csrf_secret not in response.text
        assert str(session.subject_id) not in response.text
        assert valid_csrf_cookie(session, client.cookies.get("__Host-rc_csrf"))
        second = client.get("/api/v1/me")
        assert "set-cookie" not in second.headers
        assert len(store.records) == 1


def test_http_development_exception_is_server_configured_only():
    app, _, _ = app_and_store("development")
    with TestClient(app) as client:
        response = client.get("/api/v1/me")
        assert "rc_session=" in response.headers.get_list("set-cookie")[0]
        assert "Secure" not in response.headers.get_list("set-cookie")[0]
    app, _, _ = app_and_store("production")
    with TestClient(app) as client:
        response = client.get("/api/v1/me", headers={"X-Forwarded-Proto": "http", "X-App-Env": "development"})
        assert "__Host-rc_session=" in response.headers.get_list("set-cookie")[0]
        assert "Secure" in response.headers.get_list("set-cookie")[0]


def test_known_uuid_is_not_authorization_and_private_404s_match():
    app, store, resources = app_and_store()
    with TestClient(app, base_url="https://testserver") as first, TestClient(app, base_url="https://testserver") as second:
        first.get("/api/v1/me")
        second.get("/api/v1/me")
        owner = store.records[token_digest(first.cookies.get("__Host-rc_session"))].subject_id
        resource_id = uuid4()
        resources[resource_id] = owner
        assert first.get(f"/private/{resource_id}").status_code == 200
        denied = second.get(f"/private/{resource_id}")
        absent = second.get(f"/private/{uuid4()}")
        assert denied.status_code == absent.status_code == 404
        assert denied.json()["code"] == absent.json()["code"] == "NOT_FOUND"
        assert denied.json()["message"] == absent.json()["message"]


def test_query_headers_and_unknown_cookie_do_not_select_a_subject():
    app, store, _ = app_and_store()
    chosen = "a" * 43
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get(f"/api/v1/me?session={chosen}&authenticated=true", headers={"Cookie": f"__Host-rc_session={chosen}", "X-Session-ID": chosen})
        assert response.json()["authenticated"] is False
        assert client.cookies.get("__Host-rc_session") != chosen
        assert token_digest(chosen) not in store.records


def test_duplicate_session_cookies_are_not_ambiguously_authorized():
    app, store, resources = app_and_store()
    with TestClient(app, base_url="https://testserver") as client:
        client.get("/api/v1/me")
        token = client.cookies.get("__Host-rc_session")
        resource_id = uuid4()
        resources[resource_id] = store.records[token_digest(token)].subject_id
        response = client.get(f"/private/{resource_id}", headers={"Cookie": f"__Host-rc_session={token}; __Host-rc_session={token}"})
        assert response.status_code == 404


def test_csrf_cookie_is_signed_and_bound_to_current_session():
    app, store, _ = app_and_store()
    service = app.state.session_service
    one, two = asyncio.run(service.issue()), asyncio.run(service.issue())
    token = csrf_token(one.session)
    assert valid_csrf_cookie(one.session, token)
    assert not valid_csrf_cookie(two.session, token)
    assert not valid_csrf_cookie(one.session, token[:-1] + ("0" if token[-1] != "0" else "1"))
    assert one.token not in repr(one) and one.session.csrf_secret not in repr(one)


def test_storage_failure_is_503_without_in_memory_fallback():
    class FailedStore(FakeStore):
        async def create(self, *args):
            raise StoreUnavailable

    app, _, _ = app_and_store()
    app.state.session_service = SessionService(FailedStore())
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/v1/me")
        assert response.status_code == 503 and response.json()["code"] == "SERVICE_UNAVAILABLE"
        assert "set-cookie" not in response.headers
        assert client.get("/api/v1/regions").status_code == 200


def with_redis(scenario):
    url = os.environ.get("PERSISTENCE_TEST_REDIS_URL")
    if not url:
        pytest.skip("실제 Redis 세션 검증은 CI의 Compose 통합 잡에서 실행")

    async def run():
        client = build_redis(Settings(_env_file=None, redis_url=url))
        store = RedisSessionStore(client, prefix=f"test:session:{uuid4().hex}:")
        try:
            await scenario(SessionService(store), store, client)
        finally:
            keys = [key async for key in client.scan_iter(match=store.prefix + "*")]
            if keys:
                await client.delete(*keys)
            await client.aclose()

    asyncio.run(run())


def test_real_redis_stores_hash_only_and_polling_does_not_refresh_idle():
    async def scenario(service, store, client):
        issued = await service.issue()
        key = store.key(issued.session.digest)
        values = await client.hgetall(key)
        assert issued.token not in key + repr(values)
        assert 0 < await client.pttl(key) <= IDLE_MS
        last = int(values["last_ms"]) - 60000
        await client.hset(key, mapping={"created_ms": last - 60000, "last_ms": last})
        before = await client.pttl(key)
        loaded = await service.resolve(issued.token)
        assert loaded.last_activity_ms == last
        assert await client.pttl(key) <= before
        active = await service.resolve(issued.token, touch=True)
        assert active.last_activity_ms > last

    with_redis(scenario)


@pytest.mark.parametrize("expiry", ["idle", "absolute"])
def test_real_redis_exact_expiry_never_revives_with_touch(expiry):
    async def scenario(service, store, client):
        issued = await service.issue()
        seconds, micros = await client.time()
        now = seconds * 1000 + micros // 1000
        values = {"created_ms": now - ABSOLUTE_MS, "last_ms": now} if expiry == "absolute" else {"created_ms": now - IDLE_MS, "last_ms": now - IDLE_MS}
        await client.hset(store.key(issued.session.digest), mapping=values)
        assert await service.resolve(issued.token, touch=True) is None
        assert not await client.exists(store.key(issued.session.digest))

    with_redis(scenario)


def test_real_redis_activity_and_rotation_cannot_extend_absolute_expiry():
    async def scenario(service, store, client):
        issued = await service.issue()
        seconds, micros = await client.time()
        now = seconds * 1000 + micros // 1000
        created = now - ABSOLUTE_MS + 10000
        await client.hset(store.key(issued.session.digest), mapping={"created_ms": created, "last_ms": now})
        active = await service.resolve(issued.token, touch=True)
        assert active.created_ms == created
        assert 0 < await client.pttl(store.key(active.digest)) <= 10000
        rotated = await service.rotate(issued.token)
        assert rotated.session.created_ms == created
        assert rotated.session.subject_id == issued.session.subject_id
        assert await service.resolve(issued.token) is None
        assert 0 < await client.pttl(store.key(rotated.session.digest)) <= 10000
        assert not valid_csrf_cookie(rotated.session, csrf_token(issued.session))

    with_redis(scenario)


def test_real_redis_concurrent_rotation_has_one_winner_and_revocation_is_final():
    async def scenario(service, store, client):
        issued = await service.issue()
        results = await asyncio.gather(*(service.rotate(issued.token) for _ in range(12)), return_exceptions=True)
        winners = [result for result in results if isinstance(result, IssuedSession)]
        assert len(winners) == 1
        assert all(isinstance(result, IssuedSession) or isinstance(result, AppError) and result.code == "NOT_FOUND" for result in results)
        winner = winners[0]
        assert await service.resolve(issued.token) is None
        await service.revoke(winner.token)
        assert await service.resolve(winner.token, touch=True) is None

    with_redis(scenario)
