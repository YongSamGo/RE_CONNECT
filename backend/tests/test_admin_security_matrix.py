"""W13-04: 실제 Redis·SQL 세션으로 모든 운영자 경로의 권한 우회·상태 위조를 막는지 보는 HTTP 행렬.

모듈별 시험은 운영자 판정을 대역으로 바꿔 저장소 경계만 본다. 여기서는 실제 로그인·역할·MFA 세션으로
비회원, 일반 회원, MFA를 확인하지 않은 운영자, MFA가 만료된 운영자, 역할을 회수당한 운영자가
`/admin/*`의 모든 쓰기·조회를 시도한다. 역할·계정 위조 헤더를 함께 보내고, 시도 뒤 공고 버전·공개 포인터·
검수 근거·신고·감사 기록이 하나도 바뀌지 않았는지 DB에서 다시 읽는다.
확인된 운영자도 본문으로 검수 상태·작성자를 넣거나, 헤더로 다른 계정을 주장하거나, 필터에 SQL을 넣을 수 없다.
공고·신고·운영자 신원은 모두 가상 값이다. 시나리오와 시험의 대응은 docs/security/attack-tests.md에 있다.
"""

from datetime import UTC, datetime, timedelta
import secrets
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretBytes
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import sessionmaker

from app.core.encryption import ContentCipher, EncryptionKeyRing
from app.modules.admin_opportunities.repository import SqlAdminOpportunityRepository
from app.modules.admin_opportunities.service import AdminOpportunityService
from app.modules.audit.repository import SqlAuditRepository
from app.modules.audit.service import AuditService
from app.modules.auth.service import Identity
from app.modules.operators import totp
from app.modules.operators.repository import SqlOperatorMfaRepository
from app.modules.operators.service import OperatorMfaService
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import PublicOpportunityService
from app.modules.opportunity_reviews.repository import SqlOpportunityReviewRepository
from app.modules.opportunity_reviews.service import OpportunityReviewService
from app.modules.reports.repository import SqlReportRepository
from app.modules.reports.service import ReportService
from app.modules.reports.store import RedisReportStore
from app.modules.roles.repository import SQLRoleCatalog
from app.modules.roles.service import RoleService
from app.persistence import (
    AuditEvent, OpportunityDocument, OpportunityPublication, OpportunityReview, OpportunityVersion, OpportunityWriteReceipt,
    Report, Source,
)
from tests.test_admin_opportunities import create_body
from tests.test_admin_routes import admin_routes
from tests.test_member_auth import headers, run
from tests.test_opportunity_reviews import PATHS, values
from tests.test_reports import digest

SECRET = b"fictional-totp-seed!"
REQUEST = "req_" + "d" * 32
VERIFY = "/api/v1/admin/mfa/verify"
# 운영자 역할·계정·MFA 상태를 헤더로 주장하는 위조. 서버는 세션과 DB만 믿어야 한다.
FORGED = {"X-Role": "admin", "X-User-Role": "operator", "X-MFA-Verified": "true", "X-Forwarded-For": "127.0.0.1"}
# MFA 확인 경로는 정상 시도도 실패 횟수·감사 기록을 남기므로 "DB 불변" 행렬에서 빼고 test_operator_mfa_http에서 따로 본다.
EXCLUDED = {("POST", VERIFY)}
# 감사 조회는 from·to가 필수다. 기간 검사를 통과하는 값을 넣어 권한 판정까지 가게 한다.
AUDIT = "/api/v1/admin/audit?from=2026-10-01T00:00:00Z&to=2026-10-02T00:00:00Z"


def admin_actions(pending: UUID, report: UUID):
    """(method, path, body). 운영자 경로가 새로 생기면 test_matrix_covers_every_admin_route가 실패한다."""
    base = f"/api/v1/admin/opportunities/{pending}"
    return [
        ("GET", "/api/v1/admin/role-catalog", None),
        ("GET", "/api/v1/admin/opportunities", None),
        ("POST", "/api/v1/admin/opportunities", create_body()),
        ("GET", base, None),
        ("PATCH", base, {"base_version": 1, "changes": {"title": "위조한 운영자 수정"}}),
        *[("POST", f"{base}/{action}", body) for action, body in PATHS.items()],
        ("GET", "/api/v1/admin/reports", None),
        ("PATCH", f"/api/v1/admin/reports/{report}", {"base_version": 1, "status": "in_progress", "resolution_note": None}),
        ("GET", AUDIT, None),
    ]


def wire(ctx):
    """회원 시험 앱에 운영자 경로가 쓰는 실제 SQL·Redis 저장소를 연결한다 (app.main과 같은 조합)."""
    engine, app = ctx["engine"], ctx["app"]
    cipher = ContentCipher(EncryptionKeyRing(keys={"key-v1": SecretBytes(secrets.token_bytes(32))}, active_key_id="key-v1"))
    mfa = SqlOperatorMfaRepository(sessionmaker(engine).begin, cipher)
    ctx["members"].mfa = mfa
    app.state.operator_mfa_service = OperatorMfaService(mfa, ctx["members"])
    app.state.opportunity_service = PublicOpportunityService(SqlPublicOpportunityRepository(engine.connect))
    app.state.opportunity_review_service = OpportunityReviewService(SqlOpportunityReviewRepository(engine.begin))
    app.state.admin_opportunity_service = AdminOpportunityService(SqlAdminOpportunityRepository(sessionmaker(engine).begin))
    app.state.role_service = RoleService(app.state.journey_service, SQLRoleCatalog(engine.connect))
    app.state.audit_service = AuditService(SqlAuditRepository(engine.connect, engine.begin))
    app.state.report_service = ReportService(RedisReportStore(ctx["redis"], prefix=ctx["store"].prefix + "report:"),
                                             SqlReportRepository(engine.begin, cipher), app.state.opportunity_service, digest)
    ctx["mfa"] = mfa


def seed(engine):
    """검수 대기 공고 하나와 접수된 신고 하나. 운영자 공고 등록용 수동 출처도 둔다."""
    source, pending, published, report = uuid4(), uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    with engine.begin() as db:
        db.execute(insert(Source), [
            {"id": source, "code": "fictional-matrix", "name": "가상 출처", "base_url": "https://www.1365.go.kr"},
            {"id": uuid4(), "code": "manual_50plus", "name": "가상 수동 출처", "base_url": "https://www.50plus.or.kr"},
        ])
        db.execute(insert(OpportunityDocument), [{"id": pending, "source_id": source, "external_id": "pending"},
                                                 {"id": published, "source_id": source, "external_id": "published"}])
        db.execute(insert(OpportunityVersion), [values(pending, 1, review_status="pending", reviewed_at=None),
                                                values(published, 1, review_status="approved", reviewed_at=now)])
        db.execute(insert(OpportunityPublication), {"opportunity_id": published, "version": 1})
        db.execute(insert(Report), {"id": report, "opportunity_id": published, "opportunity_version": 1, "type": "broken_link",
                                    "status": "received", "version": 1, "received_at": now, "updated_at": now})
    return pending, report


def state(engine):
    """운영자 결정이 바꿀 수 있는 모든 행. 시도 전후가 같아야 한다."""
    with engine.connect() as db:
        return {
            "versions": db.execute(select(OpportunityVersion.opportunity_id, OpportunityVersion.version, OpportunityVersion.title,
                                          OpportunityVersion.review_status, OpportunityVersion.recruitment_status,
                                          OpportunityVersion.reviewed_at).order_by(OpportunityVersion.opportunity_id, OpportunityVersion.version)).all(),
            "publications": db.execute(select(OpportunityPublication.opportunity_id, OpportunityPublication.version)
                                       .order_by(OpportunityPublication.opportunity_id)).all(),
            "reports": db.execute(select(Report.id, Report.status, Report.version, Report.updated_at)).all(),
            "counts": {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                       for model in (OpportunityDocument, OpportunityReview, OpportunityWriteReceipt, AuditEvent)},
        }


async def member(ctx, subject):
    """실제 로그인 세션을 가진 별도 브라우저. 반환값: (browser, user_id)."""
    anonymous = await ctx["sessions"].issue()
    completion = await ctx["members"].complete(anonymous.session, Identity(subject), "login")
    browser = httpx.AsyncClient(transport=httpx.ASGITransport(ctx["app"], client=("192.0.2.10", 30001)), base_url="https://testserver")
    browser.cookies.set("__Host-rc_session", completion.issued.token, domain="testserver.local", path="/")
    await browser.get("/api/v1/me")
    return browser, completion.issued.session.user_id


def code_now():
    return totp.code_at(SECRET, totp.time_step(datetime.now(UTC).timestamp()))


async def operator(ctx, subject, *, verified=True):
    """역할 부여·MFA 등록까지 마친 운영자. verified면 실제 OTP로 이 세션의 MFA를 확인한다."""
    browser, user_id = await member(ctx, subject)
    now = datetime.now(UTC)
    ctx["mfa"].grant(user_id, now=now, request_id=REQUEST)
    ctx["mfa"].enroll(user_id, SECRET, totp.time_step(now.timestamp()) - 2, now=now, request_id=REQUEST)
    if verified:
        response = await browser.post(VERIFY, json={"otp": code_now()}, headers=headers(browser))
        assert response.status_code == 200, response.text
    return browser, user_id


async def attempt(browser, method, path, body, *, impersonate=None):
    forged = {**FORGED, **({"X-User-ID": str(impersonate), "X-Account-ID": str(impersonate)} if impersonate else {})}
    return await browser.request(method, path, json=body, headers={**headers(browser), **forged, "Idempotency-Key": str(uuid4())})


def test_matrix_covers_every_admin_route():
    # 운영자 경로 수집은 응답 칸 검토 시험(test_admin_routes)과 같은 함수를 쓴다.
    pending, report = UUID(int=1), UUID(int=2)
    covered = {(method, path.split("?", 1)[0].replace(str(pending), "{opportunity_id}").replace(str(report), "{report_id}"))
               for method, path, _ in admin_actions(pending, report)}
    assert set(admin_routes()) - EXCLUDED == covered


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_every_admin_route_rejects_anonymous_member_and_unverified_expired_or_revoked_operator(backend, tmp_path):
    async def scenario(ctx, guest):
        wire(ctx)
        pending, report = seed(ctx["engine"])
        actions = admin_actions(pending, report)
        await guest.get("/api/v1/me")
        plain, plain_id = await member(ctx, "7701001")
        unverified, _ = await operator(ctx, "7701002", verified=False)
        expired, _ = await operator(ctx, "7701003")
        session = await ctx["sessions"].resolve(expired.cookies.get("__Host-rc_session"))
        await ctx["redis"].hset(ctx["store"].key(session.digest), "mfa_until_ms", session.now_ms - 1)
        revoked, revoked_id = await operator(ctx, "7701004")
        ctx["mfa"].revoke(revoked_id, now=datetime.now(UTC), request_id=REQUEST)
        # 다른 운영자 계정을 헤더로 주장해도 세션 주체만 쓴다.
        impersonated, real_operator = await operator(ctx, "7701005")
        before = state(ctx["engine"])
        cases = [
            ("anonymous", guest, {(401, "UNAUTHENTICATED")}),
            ("member", plain, {(403, "FORBIDDEN")}),
            ("unverified operator", unverified, {(403, "MFA_REQUIRED")}),
            ("expired MFA", expired, {(403, "MFA_REQUIRED")}),
            # 회수로 세션 세대가 바뀌어, 남은 쿠키는 어느 경로에서도 만료로 판정된다.
            ("revoked operator", revoked, {(401, "SESSION_EXPIRED")}),
        ]
        try:
            for name, browser, allowed in cases:
                for method, path, body in actions:
                    response = await attempt(browser, method, path, body, impersonate=real_operator)
                    assert (response.status_code, response.json()["code"]) in allowed, (name, method, path, response.text)
                    assert "위조한 운영자 수정" not in response.text
                assert state(ctx["engine"]) == before, name
            # 역할 위조 헤더가 있어도 일반 회원은 여전히 일반 회원이다.
            me = (await plain.get("/api/v1/me", headers=FORGED)).json()["user"]
            assert me["id"] == str(plain_id) and me["roles"] == ["user"] and me["mfa_verified"] is False
        finally:
            for browser in (plain, unverified, expired, revoked, impersonated):
                await browser.aclose()
    run(backend, tmp_path, scenario)


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_verified_operator_cannot_inject_review_state_actor_or_sql_and_audit_records_the_session_actor(backend, tmp_path):
    async def scenario(ctx, _guest):
        wire(ctx)
        pending, report = seed(ctx["engine"])
        browser, actor = await operator(ctx, "7702001")
        impersonated, other = await operator(ctx, "7702002")
        base = f"/api/v1/admin/opportunities/{pending}"
        injected = {"review_status": "approved", "actor_id": str(other), "reviewed_at": "2026-01-01T00:00:00Z", "version": 9}
        try:
            before = state(ctx["engine"])
            catalog = await browser.get("/api/v1/admin/role-catalog", headers=FORGED)
            assert catalog.status_code == 200 and catalog.headers["cache-control"] == "no-store"
            assert catalog.json()["items"]
            assert all(set(role) == {"id", "name", "description", "skill_tags"} for role in catalog.json()["items"])
            assert state(ctx["engine"]) == before
            writes = [
                ("POST", "/api/v1/admin/opportunities", {**create_body(), "review_status": "approved", "published_version": 1}),
                ("PATCH", base, {"base_version": 1, "changes": {"title": "x"}, "review_status": "approved"}),
                ("PATCH", base, {"base_version": 1, "changes": {"review_status": "approved", "published_version": 1}}),
                *[("POST", f"{base}/{action}", {**body, **injected}) for action, body in PATHS.items()],
                ("PATCH", f"/api/v1/admin/reports/{report}", {"base_version": 1, "status": "in_progress", "resolution_note": None,
                                                              "actor_id": str(other)}),
            ]
            for method, path, body in writes:
                response = await attempt(browser, method, path, body, impersonate=other)
                assert response.status_code == 422, (method, path, response.text)
                assert {field["reason"] for field in response.json()["fields"]} <= {"unknown_field", "invalid_value"}, response.text
            # 경로·필터의 SQL 조각은 형식 검사에서 거절하거나 글자 그대로 검색한다.
            for query in ({"review_status": "pending' OR '1'='1"}, {"page": "1 OR 1=1"}, {"page": "9" * 5000}, {"page_size": "0"}):
                assert (await browser.get("/api/v1/admin/opportunities", params=query)).status_code == 422, query
            # 공고 목록은 상한까지 읽은 뒤 서버에서 잘라 큰 페이지 번호가 SQL OFFSET으로 가지 않는다.
            huge = await browser.get("/api/v1/admin/opportunities", params={"page": str(2**63)})
            assert huge.status_code == 200 and huge.json()["items"] == []
            for query in ({"status": "received' OR '1'='1"}, {"page": str(2**63)}):
                assert (await browser.get("/api/v1/admin/reports", params=query)).status_code == 422, query
            window = {"from": "2026-10-01T00:00:00Z", "to": "2026-10-02T00:00:00Z"}
            for query in ({**window, "from": "' OR 1=1 --"}, {**window, "actor_id": str(other)}, {**window, "page": "1 OR 1=1"}):
                assert (await browser.get("/api/v1/admin/audit", params=query)).status_code == 422, query
            literal = await browser.get("/api/v1/admin/opportunities", params={"q": "' OR 1=1 --"})
            assert literal.status_code == 200 and literal.json()["total"] == 0
            # 본문은 경로마다 올바른 값을 보내, 422가 경로 변수 검증 때문인지 확인한다.
            report_update = {"base_version": 1, "status": "in_progress", "resolution_note": None}
            for method, path, body, name in (
                ("GET", "/api/v1/admin/opportunities/1%20OR%201=1", None, "opportunity_id"),
                ("PATCH", "/api/v1/admin/opportunities/' OR '1'='1", {"base_version": 1, "changes": {"title": "x"}}, "opportunity_id"),
                ("POST", "/api/v1/admin/opportunities/' OR '1'='1/approve", PATHS["approve"], "opportunity_id"),
                ("PATCH", "/api/v1/admin/reports/1;DROP TABLE reports", report_update, "report_id"),
            ):
                response = await browser.request(method, path, json=body, headers=headers(browser))
                assert response.status_code == 422, (path, response.text)
                assert response.json()["fields"] == [{"path": name, "reason": "invalid_type"}], (path, response.text)
            assert state(ctx["engine"]) == before

            # 정상 결정은 위조 헤더가 가리키는 다른 운영자가 아니라 세션 주체로 기록한다.
            approved = await attempt(browser, "POST", f"{base}/approve", PATHS["approve"], impersonate=other)
            assert approved.status_code == 200, approved.text
            assert approved.json()["review_status"] == "approved"
            with ctx["engine"].connect() as db:
                audit = db.execute(select(AuditEvent.actor_id, AuditEvent.actor_role, AuditEvent.request_id)
                                   .where(AuditEvent.action == "opportunity.approve")).one()
                assert audit == (actor, "operator", approved.headers["x-request-id"])
                assert db.scalar(select(OpportunityPublication.version).where(OpportunityPublication.opportunity_id == pending)) == 1
            # 같은 결정을 다시 보내도 상태를 되돌리거나 두 번 기록하지 않는다.
            replay = await attempt(browser, "POST", f"{base}/approve", PATHS["approve"])
            assert replay.status_code == 409, replay.text
            with ctx["engine"].connect() as db:
                assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "opportunity.approve")) == 1
        finally:
            await browser.aclose()
            await impersonated.aclose()
    run(backend, tmp_path, scenario)


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_operator_session_from_another_browser_or_after_logout_cannot_act(backend, tmp_path):
    async def scenario(ctx, _guest):
        wire(ctx)
        pending, _report = seed(ctx["engine"])
        browser, _ = await operator(ctx, "7703001")
        approve = f"/api/v1/admin/opportunities/{pending}/approve"
        token, csrf = browser.cookies.get("__Host-rc_session"), browser.cookies.get("__Host-rc_csrf")
        try:
            before = state(ctx["engine"])
            # 운영자 쿠키만 훔쳐 다른 Origin이나 다른 CSRF 값으로 보내는 요청
            async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx["app"], client=("198.51.100.7", 30001)),
                                         base_url="https://testserver") as thief:
                thief.cookies.set("__Host-rc_session", token, domain="testserver.local", path="/")
                for extra in ({"Origin": "https://attacker.example", "X-CSRF-Token": csrf}, {"Origin": "https://testserver"},
                              {"Origin": "https://testserver", "X-CSRF-Token": "forged"}):
                    response = await thief.post(approve, json=PATHS["approve"], headers=extra)
                    assert response.status_code == 403 and response.json()["code"] == "CSRF_FAILED", response.text
            assert (await browser.post("/api/v1/auth/logout", headers=headers(browser))).status_code == 204
            stale = await browser.post(approve, json=PATHS["approve"], headers={
                "Origin": "https://testserver", "X-CSRF-Token": csrf, "Cookie": f"__Host-rc_session={token}; __Host-rc_csrf={csrf}"})
            assert stale.status_code in (401, 403), stale.text
            assert state(ctx["engine"]) == before
        finally:
            await browser.aclose()
    run(backend, tmp_path, scenario)
