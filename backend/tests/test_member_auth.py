"""실제 Redis·SQL·ASGI 로그인/회수 결합 시험. 제공자 신원/코드는 가상 대역이다."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from urllib.parse import parse_qs, urlsplit

from fastapi import Request
import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.business_errors import AppError
from app.main import create_app
from app.modules.auth.accounts import SqlAccountRepository
from app.modules.auth.http import require_member
from app.modules.auth.member_store import RedisMemberStore
from app.modules.auth.members import MemberService
from app.modules.auth.repository import RedisFlowStore
from app.modules.auth.service import Identity, OAuthService
from app.modules.sessions.service import IDLE_MS, token_digest, valid_csrf_cookie
from app.persistence import User
from tests.ingestion_helpers import ingestion_database
from tests.test_kakao_auth import adapter, responses
from tests.test_sessions import with_redis


def run(backend, tmp_path, scenario):
    if not os.environ.get("PERSISTENCE_TEST_REDIS_URL"):
        pytest.skip("실제 Redis+SQL 회원 검증은 CI 통합 잡에서 실행")
    with ingestion_database(backend, tmp_path) as (engine, _source):
        async def redis_scenario(sessions, store, client):
            accounts = SqlAccountRepository(sessionmaker(engine).begin)
            app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
            member_store = RedisMemberStore(client, session_prefix=store.prefix, flow_prefix=store.prefix + "oauth:")
            members = MemberService(accounts, member_store, sessions, transition=app.state.member_service.transition)
            context = {"app": app, "accounts": accounts, "subject": 456, "requests": [], "pause": None,
                       "engine": engine, "sessions": sessions, "store": store, "members": members, "redis": client}
            async def handle(request):
                context["requests"].append(request)
                if request.url.path == "/oauth/token" and context["pause"] is not None:
                    started, release = context["pause"];started.set();await release.wait()
                changes = {"id": context["subject"]} if request.url.host == "kapi.kakao.com" else None
                return responses(request, overrides=changes)
            app.state.session_service = sessions
            app.state.member_service = members
            app.state.oauth_service = OAuthService(RedisFlowStore(client, session_prefix=store.prefix, prefix=store.prefix + "oauth:"), adapter(handle), members)

            @app.post("/api/v1/test/member")
            async def private(request: Request):
                account = await require_member(request)
                return {"id": str(account.id)}

            @app.post("/api/v1/test/reauth")
            async def reauthenticated(request: Request):
                account = await require_member(request, reauth=True)
                return {"id": str(account.id)}

            @app.post("/api/v1/test/admin")
            async def admin(request: Request):
                await require_member(request, operator=True)
                return {"ok": True}

            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://testserver") as browser:
                await scenario(context, browser)
        with_redis(redis_scenario)


def headers(browser):
    return {"Origin": "https://testserver", "X-CSRF-Token": browser.cookies.get("__Host-rc_csrf")}


async def start(browser, purpose="login"):
    response = await browser.get("/api/v1/auth/kakao/start", params={"purpose": purpose})
    assert response.status_code == 302
    return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]


async def login(browser):
    state = await start(browser)
    return await browser.get("/api/v1/auth/kakao/callback", params={"state": state, "code": "fixture-code"})


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_login_rotates_subject_cookie_csrf_and_logout_replaces_with_anonymous(backend, tmp_path):
    async def scenario(ctx, browser):
        await browser.get("/api/v1/me")
        old = browser.cookies.get("__Host-rc_session");old_csrf = browser.cookies.get("__Host-rc_csrf")
        old_session = await ctx["sessions"].resolve(old)
        await ctx["redis"].hset(ctx["store"].key(old_session.digest), mapping={"ai_notice_version": "fixture-v1", "ai_granted_ms": old_session.now_ms})
        response = await login(browser)
        assert response.headers["location"].endswith("status=success")
        current = browser.cookies.get("__Host-rc_session")
        assert old != current and old_csrf != browser.cookies.get("__Host-rc_csrf")
        assert await ctx["sessions"].resolve(old) is None
        new_session = await ctx["sessions"].resolve(current)
        assert new_session.subject_id != old_session.subject_id and new_session.user_id is not None
        assert new_session.subject_id != new_session.user_id
        assert not valid_csrf_cookie(new_session, old_csrf)
        raw = await ctx["redis"].hgetall(ctx["store"].key(new_session.digest))
        assert "ai_notice_version" not in raw and not any(key in raw for key in ("kakao_subject", "access_token", "role"))
        view = (await browser.get("/api/v1/me")).json()
        assert view["authenticated"] and view["user"]["id"] == str(new_session.user_id)
        assert view["user"]["roles"] == ["user"] and not view["user"]["mfa_verified"]
        assert (await browser.post("/api/v1/test/member", headers=headers(browser))).status_code == 200
        assert (await browser.post("/api/v1/auth/logout")).status_code == 403
        assert (await browser.post("/api/v1/auth/logout", headers=headers(browser))).status_code == 204
        assert await ctx["sessions"].resolve(current) is None
        anonymous = (await browser.get("/api/v1/me")).json()
        assert anonymous["user"] is None and not anonymous["authenticated"]
        replay = await browser.post("/api/v1/test/member", headers={"Origin": "https://testserver", "X-CSRF-Token": old_csrf,
            "Cookie": "__Host-rc_session=" + old + "; __Host-rc_csrf=" + old_csrf})
        assert replay.status_code == 403
    run(backend, tmp_path, scenario)


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_reauth_same_account_five_minutes_no_rotation_and_different_account_does_not_create_user(backend, tmp_path):
    async def scenario(ctx, browser):
        assert (await login(browser)).headers["location"].endswith("status=success")
        token = browser.cookies.get("__Host-rc_session");csrf = browser.cookies.get("__Host-rc_csrf")
        assert (await browser.post("/api/v1/test/reauth", headers=headers(browser))).status_code == 403
        state = await start(browser, "reauth")
        response = await browser.get("/api/v1/auth/kakao/callback", params={"state": state, "code": "fixture-code"})
        assert response.headers["location"].endswith("status=success") and "set-cookie" not in response.headers
        assert browser.cookies.get("__Host-rc_session") == token and browser.cookies.get("__Host-rc_csrf") == csrf
        session = await ctx["sessions"].resolve(token);binding = await ctx["members"].store.read(session.digest)
        assert 0 < binding.reauth_until_ms - binding.now_ms <= 300000
        assert (await browser.post("/api/v1/test/reauth", headers=headers(browser))).status_code == 200
        ctx["subject"] = 999
        state = await start(browser, "reauth")
        response = await browser.get("/api/v1/auth/kakao/callback", params={"state": state, "code": "fixture-code"})
        assert response.headers["location"].endswith("status=failed") and browser.cookies.get("__Host-rc_session") == token
        with ctx["engine"].connect() as db:assert db.scalar(select(func.count()).select_from(User)) == 1
        await ctx["redis"].hset(ctx["store"].key(session.digest), "reauth_until_ms", 1)
        assert (await browser.get("/api/v1/me")).json()["user"]["reauth_until"] is None
        assert (await browser.post("/api/v1/test/reauth", headers=headers(browser))).status_code == 403
    run(backend, tmp_path, scenario)


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_current_database_role_status_and_no_mfa_bypass(backend, tmp_path):
    async def scenario(ctx, browser):
        await login(browser);session = await ctx["sessions"].resolve(browser.cookies.get("__Host-rc_session"))
        assert (await browser.post("/api/v1/test/admin", headers=headers(browser))).json()["code"] == "FORBIDDEN"
        with ctx["engine"].begin() as db:db.execute(update(User).where(User.id == session.user_id).values(role="admin"))
        view = (await browser.get("/api/v1/me")).json()
        assert view["user"]["roles"] == ["operator"] and view["user"]["mfa_verified"] is False
        assert (await browser.post("/api/v1/test/admin", headers=headers(browser))).json()["code"] == "MFA_REQUIRED"
        with ctx["engine"].begin() as db:db.execute(update(User).where(User.id == session.user_id).values(role="user"))
        assert (await browser.post("/api/v1/test/admin", headers=headers(browser))).json()["code"] == "FORBIDDEN"
        with ctx["engine"].begin() as db:db.execute(update(User).where(User.id == session.user_id).values(status="suspended"))
        assert (await browser.post("/api/v1/test/member", headers=headers(browser))).status_code == 401
        assert (await browser.get("/api/v1/me")).json()["authenticated"] is False
        assert await ctx["sessions"].store.load(session.digest, touch=False) is None
    run(backend, tmp_path, scenario)


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_revoked_while_provider_waits_cannot_create_account_or_login(backend, tmp_path):
    async def scenario(ctx, browser):
        state = await start(browser)
        began, release = asyncio.Event(), asyncio.Event();ctx["pause"] = (began, release)
        pending = asyncio.create_task(browser.get("/api/v1/auth/kakao/callback", params={"state": state, "code": "fixture-code"}))
        try:
            await asyncio.wait_for(began.wait(), 5)
            assert (await browser.post("/api/v1/auth/logout", headers=headers(browser))).status_code == 204
        finally:release.set()
        result = await pending
        assert result.headers["location"].endswith("status=failed")
        with ctx["engine"].connect() as db:assert db.scalar(select(func.count()).select_from(User)) == 0
        assert not (await browser.get("/api/v1/me")).json()["authenticated"]
    run(backend, tmp_path, scenario)


def test_concurrent_callbacks_one_member_session_and_incomplete_resource_cleanup_fails_closed(tmp_path):
    async def scenario(ctx, browser):
        state = await start(browser)
        outcomes = await asyncio.gather(*(browser.get("/api/v1/auth/kakao/callback", params={"state": state, "code": "fixture-code"}) for _ in range(12)))
        assert sum(response.headers["location"].endswith("status=success") for response in outcomes) == 1
        assert len(ctx["requests"]) == 3
        assert (await browser.get("/api/v1/me")).json()["authenticated"]
        old = browser.cookies.get("__Host-rc_session")
        ctx["app"].state.journey_service = object()
        result = await login(browser)
        assert result.headers["location"].endswith("status=failed")
        assert browser.cookies.get("__Host-rc_session") == old
        assert (await browser.post("/api/v1/auth/logout", headers=headers(browser))).status_code == 503
        assert await ctx["sessions"].resolve(old) is None
        del ctx["app"].state.journey_service
        assert (await browser.get("/api/v1/me")).json()["authenticated"] is False
    run("sqlite", tmp_path, scenario)


def test_real_postgresql_concurrent_first_login_is_single_user(tmp_path):
    with ingestion_database("postgresql", tmp_path) as (engine, _source):
        accounts = SqlAccountRepository(sessionmaker(engine).begin);barrier = Barrier(6)
        def link(_):
            barrier.wait(timeout=10)
            return accounts.link(Identity("12345")).id
        with ThreadPoolExecutor(max_workers=6) as executor:ids = list(executor.map(link, range(6)))
        assert len(set(ids)) == 1
        with engine.connect() as db:assert db.scalar(select(func.count()).select_from(User)) == 1


def test_member_binding_expires_with_session_and_anonymous_rotate_cannot_drop_authentication(tmp_path):
    async def scenario(ctx, browser):
        await login(browser)
        token = browser.cookies.get("__Host-rc_session");session = await ctx["sessions"].resolve(token)
        with pytest.raises(AppError, match="SERVICE_UNAVAILABLE"):
            await ctx["sessions"].rotate(token)
        assert (await browser.get("/api/v1/me")).json()["authenticated"]
        key = ctx["store"].key(session.digest)
        now = await ctx["redis"].time();ms = now[0] * 1000 + now[1] // 1000
        await ctx["redis"].hset(key, mapping={"created_ms": ms - IDLE_MS + 10000, "last_ms": ms - IDLE_MS + 10000})
        assert (await browser.post("/api/v1/test/member", headers=headers(browser))).status_code == 200
        assert await ctx["redis"].pttl(key) > IDLE_MS - 10000
        await ctx["redis"].hset(key, mapping={"created_ms": ms - IDLE_MS - 1, "last_ms": ms - IDLE_MS - 1})
        assert (await browser.post("/api/v1/test/member", headers=headers(browser))).status_code == 403
        assert await ctx["redis"].exists(key) == 0
    run("sqlite", tmp_path, scenario)


def test_database_failure_after_redis_switch_does_not_leave_authenticated_orphan(tmp_path):
    async def scenario(ctx, browser):
        def failed_get(_uid):raise AppError("SERVICE_UNAVAILABLE")
        ctx["accounts"].get = failed_get
        result = await login(browser)
        assert result.headers["location"].endswith("status=failed") and "set-cookie" not in result.headers
        keys = [key async for key in ctx["redis"].scan_iter(match=ctx["store"].prefix + "*")]
        assert keys == []
        assert (await browser.get("/api/v1/me")).json()["authenticated"] is False
    run("sqlite", tmp_path, scenario)
