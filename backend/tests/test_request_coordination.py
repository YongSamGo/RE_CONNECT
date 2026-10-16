"""실행 중복·낡은 수정·삭제 경합을 실제 Redis에서 검증한다."""

import asyncio
from dataclasses import replace
import os
from uuid import uuid4

import pytest
import httpx
from starlette.requests import Request

from app.adapters.redis import build_redis
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.requests.http import idempotency_key
from app.modules.requests.repository import MAX_RESOURCE_REQUESTS, RedisRequestStore
from app.modules.requests.service import (
    Permit, Replay, RequestScope, RequestService, ResultReference,
    RETENTION_MS, RESOURCE_MAX_MS, UnavailableRequestStore, input_fingerprint,
)
from app.modules.sessions.http import require_session
from app.modules.sessions.repository import RedisSessionStore
from app.modules.sessions.service import SessionService


def check_error(code, callback):
    with pytest.raises(AppError) as caught:
        asyncio.run(callback())
    assert caught.value.code == code


def test_fingerprint_preserves_types_and_order_is_irrelevant():
    assert input_fingerprint({"b": 2, "a": "경험"}) == input_fingerprint({"a": "경험", "b": 2})
    assert input_fingerprint({"a": 1}) != input_fingerprint({"a": "1"})
    assert input_fingerprint({"a": None}) != input_fingerprint({})


@pytest.mark.parametrize("value", [[], {"x": float("nan")}, {"x": object()}, {"x": "x" * 65536}], ids=["not-object", "nan", "not-json", "oversize"])
def test_invalid_fingerprint_is_fixed_error(value):
    with pytest.raises(AppError, match="VALIDATION_FAILED"):
        input_fingerprint(value)


@pytest.mark.parametrize("key", ["", "../key", "x" * 10000, uuid4().hex, "{" + str(uuid4()) + "}"], ids=["empty", "path", "long", "compact", "braces"])
def test_invalid_client_key_never_reaches_store(key):
    service = RequestService(UnavailableRequestStore())
    check_error("VALIDATION_FAILED", lambda: service.begin(RequestScope(uuid4(), "messages"), key, {}))


@pytest.mark.parametrize("revision", [None, -1, True, 2**31, "1"])
def test_revision_is_bounded_integer(revision):
    service = RequestService(UnavailableRequestStore())
    check_error("VALIDATION_FAILED", lambda: service.begin(RequestScope(uuid4(), "messages", uuid4()), str(uuid4()), {}, base_revision=revision))


def test_key_header_is_single_and_missing_redis_fails_closed():
    for headers in ([], [(b"idempotency-key", b"a"), (b"idempotency-key", b"b")]):
        with pytest.raises(AppError, match="VALIDATION_FAILED"):
            idempotency_key(Request({"type": "http", "headers": headers}))
    value = str(uuid4())
    assert idempotency_key(Request({"type": "http", "headers": [(b"idempotency-key", value.encode())]})) == value
    app = create_app(Settings(_env_file=None))
    check_error("SERVICE_UNAVAILABLE", lambda: app.state.request_service.begin(RequestScope(uuid4(), "report"), value, {}))


def with_redis(scenario):
    url = os.environ.get("PERSISTENCE_TEST_REDIS_URL")
    if not url:
        pytest.skip("실제 Redis 검증은 CI의 Compose 통합 잡에서 실행")

    async def run():
        client = build_redis(Settings(_env_file=None, redis_url=url))
        store = RedisRequestStore(client, prefix=f"test:request:{uuid4().hex}:")
        try:
            await scenario(RequestService(store), store, client)
        finally:
            keys = [key async for key in client.scan_iter(match=store.prefix + "*")]
            if keys:
                await client.delete(*keys)
            await client.aclose()

    asyncio.run(run())


async def expect_error(code, call):
    with pytest.raises(AppError) as caught:
        await call
    assert caught.value.code == code
    if code == "REQUEST_IN_PROGRESS":
        assert caught.value.retry_after == 2


def test_redis_concurrent_duplicate_requests_execute_once_and_replay_reference():
    async def scenario(service, store, client):
        scope, key = RequestScope(uuid4(), "reports.create"), str(uuid4())
        async def begin():
            try:
                return await service.begin(scope, key, {"type": "wrong_deadline"})
            except AppError as exc:
                return exc.code
        claims = await asyncio.gather(*(begin() for _ in range(20)))
        permits = [value for value in claims if isinstance(value, Permit)]
        assert len(permits) == 1 and claims.count("REQUEST_IN_PROGRESS") == 19
        permit = permits[0]
        result = ResultReference("report", uuid4(), 1)
        await service.complete(permit, result)
        before = await client.pttl(store.keys(scope, permit.key_id)[0])
        assert 0 < before <= RETENTION_MS
        for _ in range(3):
            assert await service.begin(scope, key, {"type": "wrong_deadline"}) == Replay(result)
            await service.complete(permit, result)  # 완료 응답 유실 후 재시도도 멱등
        assert await client.pttl(store.keys(scope, permit.key_id)[0]) <= before
        await expect_error("IDEMPOTENCY_KEY_REUSED", service.begin(scope, key, {"type": "other"}))
        await expect_error("IDEMPOTENCY_KEY_REUSED", service.complete(permit, ResultReference("report", uuid4(), 1)))
    with_redis(scenario)


def test_redis_scope_isolation_and_no_raw_input_or_key_storage():
    async def scenario(service, store, client):
        subject, resource, key = uuid4(), uuid4(), str(uuid4())
        await service.create_resource(subject, resource, ttl_ms=RESOURCE_MAX_MS)
        scopes = [RequestScope(subject, "messages", resource), RequestScope(subject, "drafts", resource), RequestScope(uuid4(), "reports"), RequestScope(subject, "reports")]
        for scope in scopes:
            await service.begin(scope, key, {"private": "TEST_ONLY_PRIVATE_CONTENT"}, base_revision=0 if scope.resource_id else None)
        keys = [value async for value in client.scan_iter(match=store.prefix + "*")]
        for redis_key in keys:
            assert key not in redis_key
            if await client.type(redis_key) == "hash":
                values = str(await client.hgetall(redis_key))
                assert "TEST_ONLY_PRIVATE_CONTENT" not in values
                assert key not in values
        stranger = RequestScope(uuid4(), "messages", resource)
        await expect_error("NOT_FOUND", service.begin(stranger, key, {}, base_revision=0))
    with_redis(scenario)


def test_redis_cas_has_one_winner_and_replay_does_not_increment_again():
    async def scenario(service, store, client):
        subject, resource = uuid4(), uuid4()
        assert await service.create_resource(subject, resource, ttl_ms=RESOURCE_MAX_MS)
        assert not await service.create_resource(subject, resource, ttl_ms=RESOURCE_MAX_MS)
        scope = RequestScope(subject, "messages", resource)
        permits = [await service.begin(scope, str(uuid4()), {"text": str(i)}, base_revision=0) for i in range(2)]
        results = [ResultReference("message", uuid4(), 1) for _ in permits]
        async def complete(index):
            try:
                await service.complete(permits[index], results[index])
                return "ok"
            except AppError as exc:
                return exc.code
        outcomes = await asyncio.gather(complete(0), complete(1))
        assert sorted(outcomes) == ["VERSION_CONFLICT", "ok"]
        assert await client.get(store.resource_key(subject, resource)) == "1"
        winner, loser = outcomes.index("ok"), outcomes.index("VERSION_CONFLICT")
        await service.complete(permits[winner], results[winner])
        assert await client.get(store.resource_key(subject, resource)) == "1"
        assert await service.begin(scope, str(permits[winner].key_id), {"text": str(winner)}, base_revision=0) == Replay(results[winner])
        await expect_error("VERSION_CONFLICT", service.begin(scope, str(permits[loser].key_id), {"text": str(loser)}, base_revision=0))
        await expect_error("VERSION_CONFLICT", service.begin(scope, str(uuid4()), {}, base_revision=0))
        await expect_error("IDEMPOTENCY_KEY_REUSED", service.begin(scope, str(permits[winner].key_id), {"text": str(winner)}, base_revision=1))
    with_redis(scenario)


def test_redis_expiry_and_delete_prevent_late_completion_and_remove_all_api_keys():
    async def scenario(service, store, client):
        subject, resource = uuid4(), uuid4()
        await service.create_resource(subject, resource, ttl_ms=RESOURCE_MAX_MS)
        scope = RequestScope(subject, "messages", resource)
        permit = await service.begin(scope, str(uuid4()), {}, base_revision=0)
        other = await service.begin(RequestScope(subject, "drafts", resource), str(uuid4()), {}, base_revision=0)
        keep = await service.begin(RequestScope(subject, "reports"), str(uuid4()), {})
        await service.delete_resource(uuid4(), resource)  # 타 주체의 같은 식별자는 영향을 주지 않는다
        assert await client.exists(store.keys(scope, permit.key_id)[0])
        await service.delete_resource(subject, resource)
        await service.delete_resource(subject, resource)
        for value in (permit, other):
            assert not await client.exists(store.keys(value.scope, value.key_id)[0])
            await expect_error("NOT_FOUND", service.complete(value, ResultReference("message", uuid4(), 1)))
        assert await client.exists(store.keys(keep.scope, keep.key_id)[0])
        await expect_error("NOT_FOUND", service.begin(scope, str(uuid4()), {}, base_revision=0))
        await service.create_resource(subject, resource, ttl_ms=5000)
        fresh = await service.begin(scope, str(uuid4()), {}, base_revision=0)
        assert 0 < await client.pttl(store.keys(scope, fresh.key_id)[0]) <= 5000
        await client.pexpire(store.resource_key(subject, resource), 0)
        await expect_error("NOT_FOUND", service.complete(fresh, None))
    with_redis(scenario)


def test_redis_no_takeover_or_audio_replay_and_no_forged_completion():
    async def scenario(service, store, client):
        scope = RequestScope(uuid4(), "speech")
        permit = await service.begin(scope, str(uuid4()), {})
        await expect_error("IDEMPOTENCY_KEY_REUSED", service.complete(replace(permit, execution_id="0" * 64), None))
        await expect_error("REQUEST_IN_PROGRESS", service.begin(scope, str(permit.key_id), {}))
        await service.complete(permit, None)
        await expect_error("REQUEST_ALREADY_COMPLETED", service.begin(scope, str(permit.key_id), {}))
    with_redis(scenario)


def test_redis_corruption_and_connection_errors_fail_closed():
    async def scenario(service, store, client):
        scope = RequestScope(uuid4(), "reports")
        permit = await service.begin(scope, str(uuid4()), {})
        redis_key = store.keys(scope, permit.key_id)[0]
        await client.hset(redis_key, "state", "unrecognized")
        await expect_error("SERVICE_UNAVAILABLE", service.begin(scope, str(permit.key_id), {}))
        await client.delete(redis_key)
        await client.set(redis_key, "wrong-type")
        await expect_error("SERVICE_UNAVAILABLE", service.begin(scope, str(permit.key_id), {}))
        await client.aclose()
        broken = build_redis(Settings(_env_file=None, redis_url="redis://127.0.0.1:1/0"))
        try:
            await expect_error("SERVICE_UNAVAILABLE", RequestService(RedisRequestStore(broken)).begin(scope, str(uuid4()), {}))
        finally:
            await broken.aclose()
    with_redis(scenario)


def test_redis_per_resource_budget_is_bounded_and_delete_is_complete():
    async def scenario(service, store, client):
        subject, resource = uuid4(), uuid4()
        await service.create_resource(subject, resource, ttl_ms=RESOURCE_MAX_MS)
        scope = RequestScope(subject, "messages", resource)
        for _ in range(MAX_RESOURCE_REQUESTS):
            await service.begin(scope, str(uuid4()), {}, base_revision=0)
        await expect_error("RATE_LIMITED", service.begin(scope, str(uuid4()), {}, base_revision=0))
        await service.delete_resource(subject, resource)
        assert not [key async for key in client.scan_iter(match=store.prefix + "*")]
    with_redis(scenario)


def test_real_redis_http_csrf_session_scope_replay_and_fixed_conflicts():
    async def scenario(service, store, redis):
        app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
        app.state.session_service = SessionService(RedisSessionStore(redis, prefix=store.prefix + "session:"))
        app.state.request_service = service
        executed = []

        # 시험용 업무 경로. 운영 경로를 추가하거나 외부 추론을 흉내 내지 않는다.
        @app.post("/api/v1/coordination-test")
        async def change(request: Request, body: dict):
            session = await require_session(request)
            outcome = await request.app.state.request_service.begin(RequestScope(session.subject_id, "reports.create"), idempotency_key(request), body)
            if isinstance(outcome, Replay):
                result = outcome.result
            else:
                executed.append(1)
                result = ResultReference("report", uuid4(), 1)
                await request.app.state.request_service.complete(outcome, result)
            return {"id": str(result.id), "version": result.version}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://testserver") as client:
            assert (await client.get("/api/v1/me")).status_code == 200
            headers = {"Origin": "https://testserver", "X-CSRF-Token": client.cookies.get("__Host-rc_csrf"), "Idempotency-Key": str(uuid4())}
            first = await client.post("/api/v1/coordination-test", json={"type": "deadline"}, headers=headers)
            second = await client.post("/api/v1/coordination-test", json={"type": "deadline"}, headers=headers)
            assert first.status_code == second.status_code == 200 and first.json() == second.json()
            assert len(executed) == 1 and second.headers["cache-control"] == "no-store"
            conflict = await client.post("/api/v1/coordination-test", json={"type": "different"}, headers=headers)
            assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
            duplicate = await client.post("/api/v1/coordination-test", json={}, headers=list(headers.items()) + [("Idempotency-Key", str(uuid4()))])
            assert duplicate.status_code == 422
            session = await app.state.session_service.resolve(client.cookies.get("__Host-rc_session"))
            headers["Idempotency-Key"] = str(uuid4())
            await service.begin(RequestScope(session.subject_id, "reports.create"), headers["Idempotency-Key"], {})
            pending = await client.post("/api/v1/coordination-test", json={}, headers=headers)
            assert pending.status_code == 409 and pending.json()["code"] == "REQUEST_IN_PROGRESS"
            assert pending.headers["retry-after"] == "2" and len(executed) == 1
            app.state.request_service = RequestService(UnavailableRequestStore())
            unavailable = await client.post("/api/v1/coordination-test", json={}, headers=headers)
            assert unavailable.status_code == 503 and unavailable.json()["code"] == "SERVICE_UNAVAILABLE"
    with_redis(scenario)
