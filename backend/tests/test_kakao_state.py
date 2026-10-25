"""실제 Redis 원자 소모·수명·세션 결합. 카카오 코드/토큰은 저장하지 않는다."""

import asyncio
import json

from app.modules.auth.repository import RedisFlowStore
from app.modules.auth.service import Flow, state_digest
from app.modules.sessions.service import IDLE_MS
from tests.test_sessions import with_redis


def test_real_redis_one_use_concurrency_limit_three_and_revocation():
    async def scenario(sessions, store, client):
        prefix = store.prefix + "oauth:"
        flows = RedisFlowStore(client, session_prefix=store.prefix, prefix=prefix)
        one, other = await sessions.issue(), await sessions.issue()
        session = one.session
        states = [(str(i) * 43) for i in range(4)]
        try:
            for state in states:
                assert await flows.create(session.digest, state_digest(state), Flow("login", "v" * 43))
            assert await client.llen(prefix + session.digest) == 3
            assert await flows.consume(session.digest, state_digest(states[0])) is None
            assert await flows.consume(other.session.digest, state_digest(states[1])) is None
            attempts = await asyncio.gather(*(flows.consume(session.digest, state_digest(states[1])) for _ in range(20)))
            assert sum(value is not None for value in attempts) == 1
            assert await client.pttl(prefix + session.digest) <= 600000
            raw = await client.lrange(prefix + session.digest, 0, -1)
            assert states[2] not in json.dumps(raw)
            assert "code" not in json.dumps(raw) and "token" not in json.dumps(raw)
            await sessions.revoke(one.token)
            assert await flows.consume(session.digest, state_digest(states[2])) is None
        finally:
            await client.delete(prefix + session.digest)
    with_redis(scenario)


def test_real_redis_expiry_and_session_idle_cannot_be_extended_by_flow_calls():
    async def scenario(sessions, store, client):
        flows = RedisFlowStore(client, session_prefix=store.prefix, prefix=store.prefix + "oauth:")
        one = await sessions.issue(); digest = one.session.digest; key = flows.prefix + digest
        state = state_digest("a" * 43)
        try:
            await flows.create(digest, state, Flow("reauth", "v" * 43))
            raw = json.loads((await client.lrange(key, 0, -1))[0]);raw["expires"] = 1
            await client.delete(key);await client.rpush(key, json.dumps(raw))
            assert await flows.consume(digest, state) is None
            assert await client.exists(key) == 0
            await flows.create(digest, state, Flow("login", "v" * 43))
            now = await client.time();ms = now[0] * 1000 + now[1] // 1000
            await client.hset(store.key(digest), mapping={"created_ms": ms - IDLE_MS - 1, "last_ms": ms - IDLE_MS - 1})
            assert await flows.consume(digest, state) is None
            assert not await flows.create(digest, state_digest("b" * 43), Flow("login", "v" * 43))
        finally:await client.delete(key)
    with_redis(scenario)


def test_real_http_routes_and_redis_allow_only_one_concurrent_code_exchange():
    import httpx
    from urllib.parse import parse_qs, urlsplit
    from app.core.config import Settings
    from app.main import create_app
    from app.modules.auth.service import OAuthService
    from tests.test_kakao_auth import adapter, responses, FakeCompletion

    async def scenario(sessions, store, client):
        flows = RedisFlowStore(client, session_prefix=store.prefix, prefix=store.prefix + "oauth:")
        requests = []
        def handle(request):
            requests.append(request)
            return responses(request)
        app = create_app(Settings(_env_file=None, app_env="test"))
        app.state.session_service = sessions
        app.state.oauth_service = OAuthService(flows, adapter(handle), FakeCompletion())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://testserver") as browser:
            started = await browser.get("/api/v1/auth/kakao/start?purpose=login")
            state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
            outcomes = await asyncio.gather(*(browser.get("/api/v1/auth/kakao/callback", params={"state": state, "code": "fixture-code"}) for _ in range(12)))
            assert sum(r.headers["location"].endswith("status=success") for r in outcomes) == 1
            assert len(requests) == 3
    with_redis(scenario)
