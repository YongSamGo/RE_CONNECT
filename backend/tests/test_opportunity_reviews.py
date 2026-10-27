"""운영자 공고 승인·반려·비공개·종료 (W07-03 · #54). 부적절한 인가·검증되지 않은 공개를 함께 시험한다.

정상 입력과 공격 입력을 짝지어 본다: 역할/MFA 없는 주체, CSRF 없는 요청, 주체·상태 주입, 오래된 기준 버전,
공식 경로가 아닌 원문, 마감된 공고 승인, 메모의 개인정보, 감사 기록 실패 시의 부분 반영.
"""

from contextlib import contextmanager, nullcontext
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import insert, select

from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.admission.service import AdmissionService
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.versions import snapshot_from_row
from app.modules.opportunity_reviews.models import ApproveRequest, CloseRequest, HideRequest, RejectRequest, ReviewCommand
from app.modules.opportunity_reviews.repository import AUDIT_RETENTION, SqlOpportunityReviewRepository
from app.modules.opportunity_reviews.service import NotPublishable, OpportunityReviewService, check_publishable, publishability_problems
from app.modules.sessions.service import SessionService
from app.persistence import AuditEvent, Base, OpportunityDocument, OpportunityPublication, OpportunityReview, OpportunityVersion, Source
from tests.persistence_helpers import NOW, open_test_database, opportunity_values
from tests.test_consents import csrf
from tests.test_sessions import FakeStore

OFFICIAL = "https://www.1365.go.kr/vols/P9210/partcptn/timeCptn.do?type=show&progrmRegistNo=1234"
OPERATOR = uuid4()
REQUEST_ID = "req_" + "b" * 32
BACKENDS = pytest.mark.parametrize("backend", ["sqlite", "postgresql"])


def values(opportunity_id, version, **changes):
    return opportunity_values(opportunity_id, version, **{"source_url": OFFICIAL, "application_url": OFFICIAL, **changes})


def seed(db, *versions):
    """versions: (review_status, public, changes) 묶음. 공개 포인터는 public=True인 마지막 버전을 가리킨다."""
    Base.metadata.create_all(db)
    source, opportunity_id = uuid4(), uuid4()
    db.execute(insert(Source), {"id": source, "code": "fictional-" + source.hex[:8], "name": "가상 출처", "base_url": "https://example.org"})
    db.execute(insert(OpportunityDocument), {"id": opportunity_id, "source_id": source, "external_id": "1"})
    public = None
    for number, (status, is_public, changes) in enumerate(versions, start=1):
        reviewed = NOW - timedelta(days=1) if status != "pending" else None
        db.execute(insert(OpportunityVersion), values(opportunity_id, number, review_status=status, reviewed_at=reviewed, **changes))
        if is_public:
            public = number
    if public is not None:
        db.execute(insert(OpportunityPublication), {"opportunity_id": opportunity_id, "version": public})
    return opportunity_id


def command(action, base_version, *, reason_code=None, note="공식 원문 확인", request_id=REQUEST_ID):
    return ReviewCommand(action=action, base_version=base_version, reason_code=reason_code, note=note,
                         actor_id=OPERATOR, request_id=request_id, at=NOW)


def repository(db):
    @contextmanager
    def savepoint():
        # 실제 트랜잭션처럼 예외면 이 결정의 쓰기만 되돌린다.
        with db.begin_nested():
            yield db
    return SqlOpportunityReviewRepository(savepoint)


def state(db, opportunity_id):
    rows = db.execute(select(OpportunityVersion.version, OpportunityVersion.review_status, OpportunityVersion.recruitment_status,
                             OpportunityVersion.reviewed_at).where(OpportunityVersion.opportunity_id == opportunity_id)
                      .order_by(OpportunityVersion.version)).all()
    public = db.scalar(select(OpportunityPublication.version).where(OpportunityPublication.opportunity_id == opportunity_id))
    return [tuple(row) for row in rows], public


def counts(db):
    return db.scalar(select(OpportunityReview.id).limit(1)) is not None, db.scalar(select(AuditEvent.id).limit(1)) is not None


# ---- 공개 조건 (순수 규칙) ----

def snapshot(**changes):
    row = values(uuid4(), 1, **changes)
    return snapshot_from_row(row)


def test_publishable_official_detail_path_with_region_or_remote():
    assert publishability_problems(snapshot(), now=NOW) == ()
    remote = snapshot(activity_province=None, activity_district=None, remote_allowed=True)
    assert publishability_problems(remote, now=NOW) == ()


@pytest.mark.parametrize(("changes", "path", "reason"), [
    ({"activity_province": None, "activity_district": None, "remote_allowed": None}, "content.activity_region", "required"),
    ({"activity_province": None, "activity_district": None, "remote_allowed": False}, "content.activity_region", "required"),
    # HTTPS 형식은 맞지만 공식 상세 경로 허용표 밖: 피싱·임의 기관 주소, 같은 호스트의 다른 경로
    ({"source_url": "https://www.1365.go.kr.attacker.example/vols/P9210/partcptn/timeCptn.do?type=show&progrmRegistNo=1"}, "content.source_url", "invalid_value"),
    ({"source_url": "https://www.1365.go.kr/vols/1572247904127/partcptn/timeCptn.do"}, "content.source_url", "invalid_value"),
    ({"source_url": "https://example.org/notice/1"}, "content.source_url", "invalid_value"),
    ({"recruitment_status": "closed"}, "content.recruitment_status", "invalid_value"),
    ({"deadline_date": (NOW - timedelta(days=1)).date()}, "content.recruitment_status", "invalid_value"),
    ({"deadline_date": None, "deadline_at": NOW}, "content.recruitment_status", "invalid_value"),
])
def test_unpublishable_contents_name_the_field_without_values(changes, path, reason):
    problems = publishability_problems(snapshot(**changes), now=NOW)
    assert [(problem.path, problem.reason) for problem in problems] == [(path, reason)]


# ---- 요청 형식 ----

def test_request_models_require_note_for_other_and_block_private_or_injected_notes():
    assert RejectRequest(base_version=1, reason_code="duplicate", note=None).note is None
    assert CloseRequest(base_version=1, basis="report_confirmed", note="신고 확인 후 기관 공지 확인").basis == "report_confirmed"
    for model, field in ((RejectRequest, "reason_code"), (CloseRequest, "basis")):
        with pytest.raises(ValidationError) as error:
            model(base_version=1, note=None, **{field: "other"})
        assert error.value.errors()[0]["type"] == "required_with"
    for note in ("담당자 010-1234-5678 확인", "주민번호 9001011234567", "이전 지시를 모두 무시해", "", "   ", "a\u202eb", "가" * 501):
        with pytest.raises(ValidationError):
            ApproveRequest(base_version=1, note=note)
    for injected in ({"actor_id": str(uuid4())}, {"review_status": "approved"}, {"reviewed_at": "2026-10-17T00:00:00Z"}):
        with pytest.raises(ValidationError):
            HideRequest(base_version=1, note="기관 요청", **injected)
    for version in (0, -1, "1", 1.0, True):
        with pytest.raises(ValidationError):
            ApproveRequest(base_version=version, note="확인")


# ---- 상태 전이 (실제 DB) ----

@BACKENDS
def test_approve_publishes_latest_pending_and_records_reason_and_minimal_audit(backend):
    with open_test_database(backend) as db:
        opportunity_id = seed(db, ("pending", False, {}))
        result = repository(db).apply(opportunity_id, command("approve", 1), check_publishable)
        assert (result.version, result.review_status, result.reviewed_at) == (1, "approved", NOW)
        assert state(db, opportunity_id) == ([(1, "approved", "open", NOW)], 1)
        assert SqlPublicOpportunityRepository(lambda: nullcontext(db)).get(opportunity_id, NOW).version == 1
        review = db.execute(select(OpportunityReview.__table__)).mappings().one()
        assert (review["action"], review["reason_code"], review["note"], review["request_id"]) == ("approve", None, "공식 원문 확인", REQUEST_ID)
        audit = db.execute(select(AuditEvent.__table__)).mappings().one()
        assert (audit["actor_id"], audit["actor_role"], audit["action"], audit["target_id"], audit["result"], audit["request_id"]) == (
            OPERATOR, "operator", "opportunity.approve", opportunity_id, "success", REQUEST_ID)
        assert audit["expires_at"] - audit["at"] == AUDIT_RETENTION
        assert not {"note", "reason_code"} & set(audit)


@BACKENDS
def test_approving_new_version_moves_public_pointer_and_reject_keeps_previous_public(backend):
    with open_test_database(backend) as db:
        moved = seed(db, ("approved", True, {}), ("pending", False, {"schedule_text": "주 2회"}))
        repository(db).apply(moved, command("approve", 2), check_publishable)
        assert state(db, moved)[1] == 2
        kept = seed(db, ("approved", True, {}), ("pending", False, {"schedule_text": "주 3회"}))
        result = repository(db).apply(kept, command("reject", 2, reason_code="source_unverifiable"))
        assert result.review_status == "rejected"
        assert state(db, kept) == ([(1, "approved", "open", NOW - timedelta(days=1)), (2, "rejected", "open", NOW)], 1)


@BACKENDS
@pytest.mark.parametrize(("versions", "action", "base", "code"), [
    # 더 새 수집 버전이 있으면 오래된 화면 기준의 결정을 받지 않는다
    ((("pending", False, {}), ("pending", False, {"schedule_text": "새 일정"})), "approve", 1, "VERSION_CONFLICT"),
    ((("pending", False, {}), ("pending", False, {"schedule_text": "새 일정"})), "reject", 1, "VERSION_CONFLICT"),
    ((("pending", False, {}),), "approve", 9, "VERSION_CONFLICT"),
    # 끝난 상태·공개 중인 버전은 다시 승인·반려하지 않는다
    ((("approved", True, {}),), "approve", 1, "INVALID_STATE_TRANSITION"),
    ((("rejected", False, {}),), "approve", 1, "INVALID_STATE_TRANSITION"),
    ((("hidden", False, {}),), "approve", 1, "INVALID_STATE_TRANSITION"),
    ((("approved", True, {}),), "reject", 1, "INVALID_STATE_TRANSITION"),
    # 비공개·종료는 공개 중인 버전에만
    ((("pending", False, {}),), "hide", 1, "INVALID_STATE_TRANSITION"),
    ((("pending", False, {}),), "close", 1, "INVALID_STATE_TRANSITION"),
    ((("approved", True, {}), ("pending", False, {"schedule_text": "새 일정"})), "hide", 2, "VERSION_CONFLICT"),
    ((("approved", True, {}), ("approved", False, {"schedule_text": "새 일정"})), "close", 2, "VERSION_CONFLICT"),
    ((("approved", True, {"recruitment_status": "closed"}),), "close", 1, "INVALID_STATE_TRANSITION"),
])
def test_stale_or_invalid_transitions_change_nothing(backend, versions, action, base, code):
    with open_test_database(backend) as db:
        opportunity_id = seed(db, *versions)
        before = state(db, opportunity_id)
        reason = {"reject": "duplicate", "close": "source_closed"}.get(action)
        with pytest.raises(AppError) as error:
            repository(db).apply(opportunity_id, command(action, base, reason_code=reason), check_publishable)
        assert error.value.code == code
        assert state(db, opportunity_id) == before and counts(db) == (False, False)


@BACKENDS
def test_unknown_opportunity_is_not_found(backend):
    with open_test_database(backend) as db:
        seed(db, ("pending", False, {}))
        with pytest.raises(AppError) as error:
            repository(db).apply(uuid4(), command("approve", 1), check_publishable)
        assert error.value.code == "NOT_FOUND"


@BACKENDS
def test_unpublishable_or_closed_pending_is_not_approved(backend):
    with open_test_database(backend) as db:
        unofficial = seed(db, ("pending", False, {"source_url": "https://example.org/notice/1"}))
        expired = seed(db, ("pending", False, {"deadline_date": (NOW - timedelta(days=1)).date()}))
        for opportunity_id, path in ((unofficial, "content.source_url"), (expired, "content.recruitment_status")):
            with pytest.raises(NotPublishable) as error:
                repository(db).apply(opportunity_id, command("approve", 1), check_publishable)
            assert [problem.path for problem in error.value.problems] == [path]
            assert state(db, opportunity_id) == ([(1, "pending", "open", None)], None)
        assert counts(db) == (False, False)


@BACKENDS
def test_hide_withdraws_public_copy_and_hidden_version_needs_a_new_version(backend):
    with open_test_database(backend) as db:
        opportunity_id = seed(db, ("approved", True, {}))
        result = repository(db).apply(opportunity_id, command("hide", 1, note="기관 요청으로 비공개"))
        assert (result.review_status, result.reviewed_at) == ("hidden", NOW)
        assert state(db, opportunity_id) == ([(1, "hidden", "open", NOW)], None)
        assert SqlPublicOpportunityRepository(lambda: nullcontext(db)).get(opportunity_id, NOW) is None
        with pytest.raises(AppError) as error:
            repository(db).apply(opportunity_id, command("approve", 1), check_publishable)
        assert error.value.code == "INVALID_STATE_TRANSITION"
        db.execute(insert(OpportunityVersion), values(opportunity_id, 2))
        assert repository(db).apply(opportunity_id, command("approve", 2), check_publishable).review_status == "approved"
        assert state(db, opportunity_id)[1] == 2


@BACKENDS
def test_close_applies_to_public_and_later_pending_without_touching_review_time(backend):
    with open_test_database(backend) as db:
        opportunity_id = seed(db, ("approved", True, {}), ("rejected", False, {"schedule_text": "반려본"}),
                              ("pending", False, {"schedule_text": "종료 전에 들어온 모집 중 버전"}))
        result = repository(db).apply(opportunity_id, command("close", 1, reason_code="report_confirmed"))
        reviewed = NOW - timedelta(days=1)
        assert (result.review_status, result.reviewed_at) == ("approved", reviewed)
        assert state(db, opportunity_id) == ([(1, "approved", "closed", reviewed), (2, "rejected", "open", reviewed),
                                             (3, "pending", "closed", None)], 1)
        public = SqlPublicOpportunityRepository(lambda: nullcontext(db))
        assert public.get(opportunity_id, NOW).recruitment_status == "closed" and public.recommendation_candidates(NOW) == []
        # 종료 전에 들어온 버전을 나중에 승인해도 다시 열리지 않는다
        with pytest.raises(NotPublishable):
            repository(db).apply(opportunity_id, command("approve", 3), check_publishable)
        review = db.execute(select(OpportunityReview.reason_code, OpportunityReview.note)).one()
        assert tuple(review) == ("report_confirmed", "공식 원문 확인")


@BACKENDS
def test_audit_failure_rolls_back_state_and_reason(backend):
    with open_test_database(backend) as db:
        opportunity_id = seed(db, ("approved", True, {}))
        before = state(db, opportunity_id)
        with pytest.raises(AppError) as error:
            repository(db).apply(opportunity_id, command("hide", 1, request_id="short"))
        assert error.value.code == "SERVICE_UNAVAILABLE"
        assert state(db, opportunity_id) == before and counts(db) == (False, False)


# ---- HTTP 경계 ----

class Members:
    """서버 역할·MFA 판정 자리. 실제 MFA 미연결 상태에서 운영자도 막히는 것은 test_member_auth가 본다."""

    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    async def require(self, session, *, reauth=False, operator=False):
        self.calls.append(operator)
        if isinstance(self.outcome, str):
            raise AppError(self.outcome)
        return self.outcome


class RecordingService:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def __getattr__(self, action):
        def run(opportunity_id, body, *, actor_id, request_id):
            self.calls.append((action, opportunity_id, body, actor_id, request_id))
            if self.error is not None:
                raise self.error
            return SimpleNamespace(model_dump=lambda mode: {"id": str(opportunity_id), "version": body.base_version,
                                                            "review_status": "approved", "reviewed_at": "2026-10-17T00:00:00Z"})
        return run


class Limits:
    async def check_http(self, identities, member):
        return None


def client_for(members, service):
    app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
    app.state.session_service = SessionService(FakeStore())
    app.state.admission_service = AdmissionService(Limits(), identity_key=bytes(range(32)))
    app.state.opportunity_review_service = service
    client = TestClient(app, base_url="https://testserver", client=("192.0.2.1", 50000), raise_server_exceptions=False)
    client.get("/api/v1/me")  # 익명 세션과 CSRF 쿠키를 받은 뒤 회원 판정 자리를 바꾼다
    app.state.member_service = members
    return client


PATHS = {
    "approve": {"base_version": 1, "note": "1365 원문과 마감일 확인"},
    "reject": {"base_version": 1, "reason_code": "source_unverifiable", "note": None},
    "hide": {"base_version": 1, "note": "기관 요청으로 비공개"},
    "close": {"base_version": 1, "basis": "organization_notice", "note": None},
}


@pytest.mark.parametrize("action", PATHS)
@pytest.mark.parametrize("outcome", ["UNAUTHENTICATED", "FORBIDDEN", "MFA_REQUIRED"])
def test_non_operator_or_unverified_operator_never_reaches_review(action, outcome):
    members, service = Members(outcome), RecordingService()
    with client_for(members, service) as client:
        response = client.post(f"/api/v1/admin/opportunities/{uuid4()}/{action}", json=PATHS[action], headers=csrf(client))
        assert response.json()["code"] == outcome and response.status_code in (401, 403)
        assert members.calls == [True] and service.calls == []


@pytest.mark.parametrize("action", PATHS)
def test_operator_decision_uses_server_actor_and_request_id(action):
    account = SimpleNamespace(id=OPERATOR, role="admin")
    service = RecordingService()
    with client_for(Members(account), service) as client:
        opportunity_id = uuid4()
        response = client.post(f"/api/v1/admin/opportunities/{opportunity_id}/{action}", json=PATHS[action], headers=csrf(client))
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        (name, target, body, actor, request_id), = service.calls
        assert (name, target, body.base_version, actor, request_id) == (action, opportunity_id, 1, OPERATOR, response.headers["x-request-id"])


def test_csrf_query_injection_and_private_notes_are_rejected_before_review():
    account = SimpleNamespace(id=OPERATOR, role="admin")
    members, service = Members(account), RecordingService()
    with client_for(members, service) as client:
        url = f"/api/v1/admin/opportunities/{uuid4()}/approve"
        assert client.post(url, json=PATHS["approve"]).json()["code"] == "CSRF_FAILED"
        assert client.post(url, json=PATHS["approve"], headers={"Origin": "https://attacker.example", "X-CSRF-Token": client.cookies.get("__Host-rc_csrf")}).json()["code"] == "CSRF_FAILED"
        assert client.post(url + "?actor_id=" + str(uuid4()), json=PATHS["approve"], headers=csrf(client)).status_code == 422
        injected = client.post(url, json={**PATHS["approve"], "actor_id": str(uuid4()), "review_status": "approved"}, headers=csrf(client))
        assert injected.status_code == 422 and {f["reason"] for f in injected.json()["fields"]} == {"unknown_field"}
        private = client.post(url, json={**PATHS["approve"], "note": "담당자 연락처 010-1234-5678"}, headers=csrf(client))
        assert private.status_code == 422 and private.json()["fields"] == [{"path": "note", "reason": "invalid_value"}]
        assert "010-1234-5678" not in private.text
        other = client.post(url.replace("approve", "reject"), json={"base_version": 1, "reason_code": "other", "note": None}, headers=csrf(client))
        assert other.json()["fields"] == [{"path": "note", "reason": "required_with"}]
        assert client.post("/api/v1/admin/opportunities/not-a-uuid/approve", json=PATHS["approve"], headers=csrf(client)).status_code == 422
        assert service.calls == []


def test_unpublishable_approval_returns_field_paths_only():
    account = SimpleNamespace(id=OPERATOR, role="admin")
    problems = publishability_problems(snapshot(activity_province=None, activity_district=None, remote_allowed=None,
                                                source_url="https://example.org/notice/1"), now=NOW)
    with client_for(Members(account), RecordingService(NotPublishable(problems))) as client:
        response = client.post(f"/api/v1/admin/opportunities/{uuid4()}/approve", json=PATHS["approve"], headers=csrf(client))
        assert response.status_code == 422 and response.json()["code"] == "VALIDATION_FAILED"
        assert response.json()["fields"] == [{"path": "content.activity_region", "reason": "required"},
                                             {"path": "content.source_url", "reason": "invalid_value"}]
        assert "example.org" not in response.text


@pytest.mark.parametrize("code", ["NOT_FOUND", "VERSION_CONFLICT", "INVALID_STATE_TRANSITION", "SERVICE_UNAVAILABLE"])
def test_review_errors_keep_common_error_contract(code):
    account = SimpleNamespace(id=OPERATOR, role="admin")
    with client_for(Members(account), RecordingService(AppError(code))) as client:
        response = client.post(f"/api/v1/admin/opportunities/{uuid4()}/hide", json=PATHS["hide"], headers=csrf(client))
        assert response.json()["code"] == code and set(response.json()) == {"code", "message", "request_id"}


def test_end_to_end_approval_links_audit_to_response_request_id():
    with open_test_database("sqlite") as db:
        opportunity_id = seed(db, ("pending", False, {}))
        account = SimpleNamespace(id=OPERATOR, role="admin")
        service = OpportunityReviewService(repository(db), clock=lambda: NOW)
        with client_for(Members(account), service) as client:
            response = client.post(f"/api/v1/admin/opportunities/{opportunity_id}/approve", json=PATHS["approve"], headers=csrf(client))
            assert response.status_code == 200
            assert response.json() == {"id": str(opportunity_id), "version": 1, "review_status": "approved", "reviewed_at": "2026-10-17T00:00:00Z"}
            assert db.scalar(select(AuditEvent.request_id)) == response.headers["x-request-id"]
            assert db.scalar(select(OpportunityReview.request_id)) == response.headers["x-request-id"]


def test_unconfigured_database_fails_closed():
    account = SimpleNamespace(id=OPERATOR, role="admin")
    app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
    with pytest.raises(AppError) as error:
        app.state.opportunity_review_service.approve(uuid4(), ApproveRequest(base_version=1, note="확인"), actor_id=account.id, request_id=REQUEST_ID)
    assert error.value.code == "SERVICE_UNAVAILABLE"
