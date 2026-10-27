"""실제 Redis·SQL·ASGI로 운영자 MFA 확인과 세션 결합을 검증한다 (W07-01, 적절한 인증 없는 중요기능 허용 SEC-01).

공격 입력: 일반 회원·익명의 확인 시도, CSRF 없는 요청, OTP 재사용, 연속 실패 후 정답, 재로그인으로 잠금 우회,
이전 세션 쿠키 재사용, MFA 만료·역할 회수·재등록 뒤 관리 API 호출. 제공자 신원·비밀값은 가상 값이다.
"""

from datetime import UTC, datetime
import secrets
from uuid import uuid4

import pytest
from pydantic import SecretBytes
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.core.encryption import ContentCipher, EncryptionKeyRing
from app.modules.operators import totp
from app.modules.operators.repository import SqlOperatorMfaRepository
from app.modules.operators.service import OperatorMfaService
from app.persistence import AuditEvent, OperatorMfaCredential
from tests.test_member_auth import headers, login, run

SECRET = b"fictional-totp-seed!"
REQUEST = "req_" + "b" * 32
VERIFY = "/api/v1/admin/mfa/verify"


def operator_scenario(body):
    """회원 시험 앱에 실제 MFA 저장소를 연결하고 로그인한 회원을 운영자로 등록한다."""
    async def scenario(ctx, browser):
        cipher = ContentCipher(EncryptionKeyRing(keys={"key-v1": SecretBytes(secrets.token_bytes(32))}, active_key_id="key-v1"))
        repository = SqlOperatorMfaRepository(sessionmaker(ctx["engine"]).begin, cipher)
        ctx["members"].mfa = repository
        ctx["app"].state.operator_mfa_service = OperatorMfaService(repository, ctx["members"])
        ctx["mfa"] = repository
        await login(browser)
        session = await ctx["sessions"].resolve(browser.cookies.get("__Host-rc_session"))
        ctx["user_id"] = session.user_id
        await body(ctx, browser)
    return scenario


def enroll(ctx):
    now = datetime.now(UTC)
    ctx["mfa"].grant(ctx["user_id"], now=now, request_id=REQUEST)
    # 등록 확인 구간은 지금보다 앞이라 현재 코드는 새 코드다.
    return ctx["mfa"].enroll(ctx["user_id"], SECRET, totp.time_step(now.timestamp()) - 2, now=now, request_id=REQUEST)


def current_code():
    return totp.code_at(SECRET, totp.time_step(datetime.now(UTC).timestamp()))


def wrong_code():
    return "000000" if current_code() != "000000" else "111111"


async def verify(browser, otp):
    return await browser.post(VERIFY, json={"otp": otp}, headers=headers(browser))


async def admin(browser):
    return await browser.post("/api/v1/test/admin", headers=headers(browser))


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_verified_otp_rotates_session_and_unlocks_admin_only_for_that_session(backend, tmp_path):
    async def body(ctx, browser):
        enroll(ctx)
        assert (await admin(browser)).json()["code"] == "MFA_REQUIRED"
        assert (await browser.get("/api/v1/me")).json()["user"]["mfa_verified"] is False
        assert (await browser.post(VERIFY, json={"otp": current_code()})).json()["code"] == "CSRF_FAILED"
        assert (await verify(browser, "12ab")).status_code == 422
        assert (await browser.post(VERIFY, json={"otp": current_code(), "role": "admin"}, headers=headers(browser))).status_code == 422
        rejected = await verify(browser, wrong_code())
        assert rejected.status_code == 403 and rejected.json()["code"] == "MFA_INVALID"

        old_session, old_csrf = browser.cookies.get("__Host-rc_session"), browser.cookies.get("__Host-rc_csrf")
        otp = current_code()
        accepted = await verify(browser, otp)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["mfa_verified"] is True and accepted.json()["expires_at"].endswith("Z")
        assert accepted.headers["cache-control"] == "no-store"
        # 권한 상승 시 세션·CSRF를 교체하고 이전 세션은 폐기한다.
        assert browser.cookies.get("__Host-rc_session") != old_session and browser.cookies.get("__Host-rc_csrf") != old_csrf
        assert await ctx["sessions"].resolve(old_session) is None
        assert (await browser.get("/api/v1/me")).json()["user"]["mfa_verified"] is True
        assert (await admin(browser)).status_code == 200

        replay = await verify(browser, otp)
        assert replay.json()["code"] == "MFA_INVALID"
        stale = await browser.post("/api/v1/test/admin", headers={"Origin": "https://testserver", "X-CSRF-Token": old_csrf,
                                   "Cookie": f"__Host-rc_session={old_session}; __Host-rc_csrf={old_csrf}"})
        assert stale.status_code == 403
        raw = await ctx["redis"].hgetall(ctx["store"].key((await ctx["sessions"].resolve(browser.cookies.get("__Host-rc_session"))).digest))
        assert otp not in repr(raw) and SECRET.hex() not in repr(raw)
        with ctx["engine"].connect() as db:
            assert {row.action for row in db.execute(select(AuditEvent.action))} >= {"mfa.verify", "mfa.fail"}

        # 새 로그인 세션에는 MFA 확인을 복사하지 않는다.
        await login(browser)
        assert (await browser.get("/api/v1/me")).json()["user"]["mfa_verified"] is False
        assert (await admin(browser)).json()["code"] == "MFA_REQUIRED"
    run(backend, tmp_path, operator_scenario(body))


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_mfa_expiry_reenrollment_and_role_revocation_block_admin_immediately(backend, tmp_path):
    async def body(ctx, browser):
        enroll(ctx)
        assert (await verify(browser, current_code())).status_code == 200
        assert (await admin(browser)).status_code == 200
        session = await ctx["sessions"].resolve(browser.cookies.get("__Host-rc_session"))
        key = ctx["store"].key(session.digest)

        await ctx["redis"].hset(key, "mfa_until_ms", session.now_ms - 1)
        assert (await admin(browser)).json()["code"] == "MFA_REQUIRED"
        assert (await browser.get("/api/v1/me")).json()["user"]["mfa_verified"] is False

        await ctx["redis"].hset(key, "mfa_until_ms", session.now_ms + 60_000)
        assert (await admin(browser)).status_code == 200
        # 재등록 등으로 자격 ID가 바뀌면 세대 변경 없이도 이전 확인은 무효다.
        with ctx["engine"].begin() as db:
            original = db.scalar(select(OperatorMfaCredential.credential_id))
            db.execute(update(OperatorMfaCredential).values(credential_id=uuid4()))
        assert (await admin(browser)).json()["code"] == "MFA_REQUIRED"
        with ctx["engine"].begin() as db:
            db.execute(update(OperatorMfaCredential).values(credential_id=original))
        assert (await admin(browser)).status_code == 200

        ctx["mfa"].revoke(ctx["user_id"], now=datetime.now(UTC), request_id=REQUEST)
        revoked = await admin(browser)
        assert revoked.status_code == 401 and revoked.json()["code"] == "SESSION_EXPIRED"
        assert (await browser.get("/api/v1/me")).json()["authenticated"] is False
    run(backend, tmp_path, operator_scenario(body))


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_lock_is_per_account_and_survives_relogin(backend, tmp_path):
    async def body(ctx, browser):
        enroll(ctx)
        statuses = [(await verify(browser, wrong_code())).status_code for _ in range(5)]
        assert statuses == [403, 403, 403, 403, 429]
        await login(browser)
        locked = await verify(browser, current_code())
        assert locked.status_code == 429 and locked.json()["code"] == "MFA_LOCKED"
        assert 1 <= int(locked.headers["retry-after"]) <= 900
        assert (await admin(browser)).json()["code"] == "MFA_REQUIRED"
    run(backend, tmp_path, operator_scenario(body))


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_member_without_operator_role_and_anonymous_cannot_use_verify(backend, tmp_path):
    async def body(ctx, browser):
        forbidden = await verify(browser, current_code())
        assert forbidden.status_code == 403 and forbidden.json()["code"] == "FORBIDDEN"
        with ctx["engine"].connect() as db:
            assert db.execute(select(AuditEvent)).all() == []
        assert (await browser.post("/api/v1/auth/logout", headers=headers(browser))).status_code == 204
        await browser.get("/api/v1/me")
        anonymous = await verify(browser, current_code())
        assert anonymous.status_code == 401 and anonymous.json()["code"] == "UNAUTHENTICATED"
    run(backend, tmp_path, operator_scenario(body))
