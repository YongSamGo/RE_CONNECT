"""운영자 감사 기록 조회·30일 정리 (W07-06 · #57). 부적절한 인가·보안기능 결정 입력 조작을 함께 시험한다.

정상 입력과 공격 입력을 짝지어 본다: 기간·페이지 조회, 만료 기록 제외, 정리 명령 / 역할·MFA 없는 주체,
계약 밖 쿼리(행위자·행위 필터 주입), 30일 초과·뒤집힌·시간대 없는 기간, 저장값이 계약 밖일 때.
"""

import json
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import get_args
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import insert, select

import manage_audit
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.audit.models import ActorRole, AuditAction, AuditResult, AuditSearch, TargetType
from app.modules.audit.repository import SqlAuditRepository
from app.modules.audit.service import AuditService
from app.modules.opportunity_reviews.service import OpportunityReviewService
from app.persistence import AuditEvent, Base
from app.persistence.operations import AUDIT_RETENTION
from tests.persistence_helpers import NOW, open_test_database
from tests.test_consents import csrf
from tests.test_opportunity_reviews import OPERATOR, PATHS, Members, client_for, repository as review_repository, seed

BACKENDS = pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
URL = "/api/v1/admin/audit"
WINDOW = {"from": "2026-10-10T00:00:00Z", "to": "2026-10-17T00:00:00Z"}


def event(at, *, expires_at=None, action="opportunity.approve", request_id=None, **changes):
    return {"id": uuid4(), "at": at, "actor_id": OPERATOR, "actor_role": "operator", "action": action,
            "target_type": "opportunity", "target_id": uuid4(), "result": "success",
            "request_id": request_id or "req_" + uuid4().hex, "expires_at": expires_at or at + AUDIT_RETENTION, **changes}


def repository(db):
    @contextmanager
    def connection():
        with db.begin_nested():
            yield db
    return SqlAuditRepository(connection, connection)


def search(**changes):
    return AuditSearch.model_validate({**WINDOW, **changes})


# ---- 조회 조건 (순수 규칙) ----

def test_search_accepts_half_open_window_up_to_retention_and_normalizes_to_utc():
    value = AuditSearch.model_validate({"from": "2026-10-01T09:00:00+09:00", "to": "2026-10-31T00:00:00Z"})
    assert (value.start.isoformat(), value.end - value.start, value.page, value.page_size) == (
        "2026-10-01T00:00:00+00:00", AUDIT_RETENTION, 1, 20)


@pytest.mark.parametrize(("changes", "path"), [
    ({"to": WINDOW["from"]}, "to"),                                  # 길이 0
    ({"to": "2026-10-09T00:00:00Z"}, "to"),                          # 뒤집힌 기간
    ({"from": "2026-09-16T23:59:59Z"}, "to"),                        # 30일 초과
    ({"from": "2026-10-10T00:00:00"}, "from"),                       # 시간대 없음
    ({"to": "not-a-time"}, "to"),
    ({"page": 0}, "page"), ({"page": 2**31}, "page"), ({"page_size": 21}, "page_size"), ({"page_size": 0}, "page_size"),
    ({"actor_id": str(uuid4())}, "actor_id"), ({"action": "opportunity.approve"}, "action"), ({"now": "2026-01-01T00:00:00Z"}, "now"),
])
def test_search_rejects_out_of_contract_queries(changes, path):
    with pytest.raises(ValidationError) as error:
        search(**changes)
    assert [item["loc"] for item in error.value.errors()] == [(path,)]


def test_audit_view_enums_match_api_contract():
    # 표준 라이브러리로 AuditEvent 블록만 대조한다 (test_business_errors와 같은 방식).
    text = (Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml").read_text(encoding="utf-8")
    block = text.split("    AuditEvent:\n", 1)[1].split("    AuditList:\n", 1)[0]
    actions = {line.strip()[2:] for line in block.split("action:", 1)[1].split("target_type:", 1)[0].splitlines()
               if line.strip().startswith("- ")}
    assert set(get_args(AuditAction)) == actions
    for field, literal in (("actor_role", ActorRole), ("target_type", TargetType), ("result", AuditResult)):
        line = next(line for line in block.splitlines() if line.strip().startswith(field + ":"))
        listed = {value.strip() for value in line.split("enum: [", 1)[1].split("]", 1)[0].split(",")} - {"null"}
        assert set(get_args(literal)) == listed, field


# ---- 조회·정리 (실제 DB) ----

@BACKENDS
def test_page_returns_window_newest_first_and_hides_expired_before_prune(backend):
    with open_test_database(backend) as db:
        Base.metadata.create_all(db)
        start = NOW - timedelta(days=7)
        inside = [event(start), event(start + timedelta(days=1)), event(NOW - timedelta(seconds=1))]
        outside = [event(start - timedelta(seconds=1)), event(NOW)]                      # from 포함, to 제외
        expired = event(start + timedelta(days=2), expires_at=NOW - timedelta(seconds=1))  # 정리 전이어도 숨김
        db.execute(insert(AuditEvent), [*inside, *outside, expired])
        page = repository(db).page(search(), NOW)
        assert (page.total, page.page, page.page_size) == (3, 1, 20)
        assert [item.event_id for item in page.items] == [row["id"] for row in reversed(inside)]
        first = page.items[0]
        assert first.model_dump(mode="json") == {
            "event_id": str(inside[2]["id"]), "at": "2026-10-16T23:59:59Z", "actor_id": str(OPERATOR), "actor_role": "operator",
            "action": "opportunity.approve", "target_type": "opportunity", "target_id": str(inside[2]["target_id"]),
            "result": "success", "request_id": inside[2]["request_id"]}


@BACKENDS
def test_pages_split_by_size_and_past_last_page_is_empty(backend):
    with open_test_database(backend) as db:
        Base.metadata.create_all(db)
        rows = [event(NOW - timedelta(hours=hour)) for hour in range(1, 6)]
        db.execute(insert(AuditEvent), rows)
        pages = [repository(db).page(search(page=number, page_size=2), NOW) for number in (1, 2, 3, 4)]
        assert [page.total for page in pages] == [5] * 4
        assert [[item.event_id for item in page.items] for page in pages] == [
            [rows[0]["id"], rows[1]["id"]], [rows[2]["id"], rows[3]["id"]], [rows[4]["id"]], []]


@BACKENDS
def test_same_time_events_have_stable_order(backend):
    with open_test_database(backend) as db:
        Base.metadata.create_all(db)
        rows = [event(NOW - timedelta(hours=1)) for _ in range(3)]
        db.execute(insert(AuditEvent), rows)
        first = [item.event_id for item in repository(db).page(search(page_size=2), NOW).items]
        second = [item.event_id for item in repository(db).page(search(page=2, page_size=2), NOW).items]
        assert sorted(first + second) == sorted(row["id"] for row in rows) and len(set(first + second)) == 3


@BACKENDS
def test_prune_removes_only_expired_events(backend):
    with open_test_database(backend) as db:
        Base.metadata.create_all(db)
        keep = event(NOW - timedelta(days=1))
        db.execute(insert(AuditEvent), [event(NOW - AUDIT_RETENTION - timedelta(days=1)),
                                        event(NOW - AUDIT_RETENTION), keep])  # expires_at == now 도 만료
        assert AuditService(repository(db), clock=lambda: NOW).prune() == 2
        assert db.scalars(select(AuditEvent.id)).all() == [keep["id"]]
        assert AuditService(repository(db), clock=lambda: NOW).prune() == 0


@BACKENDS
def test_out_of_contract_stored_value_fails_closed(backend):
    with open_test_database(backend) as db:
        Base.metadata.create_all(db)
        db.execute(insert(AuditEvent), event(NOW - timedelta(hours=1), request_id="req_not-contract-id"))
        with pytest.raises(AppError) as error:
            repository(db).page(search(), NOW)
        assert error.value.code == "SERVICE_UNAVAILABLE"


# ---- HTTP 경계 ----

class RecordingAudit:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def page(self, value):
        self.calls.append(value)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(model_dump=lambda mode: {"items": [], "page": value.page, "page_size": value.page_size, "total": 0})


def audit_client(members, service):
    client = client_for(members, None)
    client.app.state.audit_service = service
    return client


@pytest.mark.parametrize("outcome", ["UNAUTHENTICATED", "FORBIDDEN", "MFA_REQUIRED"])
def test_non_operator_or_unverified_operator_never_reads_audit(outcome):
    members, service = Members(outcome), RecordingAudit()
    with audit_client(members, service) as client:
        response = client.get(URL, params=WINDOW)
        assert response.json()["code"] == outcome and response.status_code in (401, 403)
        assert members.calls == [True] and service.calls == []


def test_operator_reads_audit_with_server_checked_window():
    service = RecordingAudit()
    with audit_client(Members(SimpleNamespace(id=OPERATOR, role="admin")), service) as client:
        response = client.get(URL, params={**WINDOW, "page": 2, "page_size": 5})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json() == {"items": [], "page": 2, "page_size": 5, "total": 0}
        (value,) = service.calls
        assert (value.start.isoformat(), value.end.isoformat()) == ("2026-10-10T00:00:00+00:00", "2026-10-17T00:00:00+00:00")


@pytest.mark.parametrize(("params", "fields"), [
    ({**WINDOW, "actor_id": str(uuid4())}, [{"path": "actor_id", "reason": "unknown_field"}]),
    ({**WINDOW, "action": "opportunity.approve"}, [{"path": "action", "reason": "unknown_field"}]),
    ({"to": WINDOW["to"]}, [{"path": "from", "reason": "required"}]),
    ({"from": "2026-09-01T00:00:00Z", "to": WINDOW["to"]}, [{"path": "to", "reason": "invalid_value"}]),
    ({**WINDOW, "from": "2026-10-10T00:00:00"}, [{"path": "from", "reason": "invalid_value"}]),
    ({**WINDOW, "page_size": 100}, [{"path": "page_size", "reason": "out_of_range"}]),
])
def test_out_of_contract_queries_are_rejected_before_reading(params, fields):
    service = RecordingAudit()
    with audit_client(Members(SimpleNamespace(id=OPERATOR, role="admin")), service) as client:
        response = client.get(URL, params=params)
        assert response.status_code == 422 and response.json()["fields"] == fields
        assert service.calls == []


def test_audit_errors_keep_common_error_contract():
    with audit_client(Members(SimpleNamespace(id=OPERATOR, role="admin")), RecordingAudit(AppError("SERVICE_UNAVAILABLE"))) as client:
        response = client.get(URL, params=WINDOW)
        assert response.status_code == 503 and set(response.json()) == {"code", "message", "request_id"}


def test_end_to_end_review_is_traceable_without_its_note():
    with open_test_database("sqlite") as db:
        opportunity_id = seed(db, ("pending", False, {}))
        operator = Members(SimpleNamespace(id=OPERATOR, role="admin"))
        with audit_client(operator, AuditService(repository(db), clock=lambda: NOW + timedelta(minutes=1))) as client:
            client.app.state.opportunity_review_service = OpportunityReviewService(review_repository(db), clock=lambda: NOW)
            approved = client.post(f"/api/v1/admin/opportunities/{opportunity_id}/approve", json=PATHS["approve"], headers=csrf(client))
            assert approved.status_code == 200
            listed = client.get(URL, params={"from": "2026-10-16T00:00:00Z", "to": "2026-10-18T00:00:00Z"})
            assert listed.status_code == 200 and listed.json()["total"] == 1
            (item,) = listed.json()["items"]
            assert (item["action"], item["target_id"], item["actor_id"], item["request_id"]) == (
                "opportunity.approve", str(opportunity_id), str(OPERATOR), approved.headers["x-request-id"])
            assert PATHS["approve"]["note"] not in listed.text


def test_unconfigured_database_fails_closed():
    app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
    for call in (lambda: app.state.audit_service.page(search()), app.state.audit_service.prune):
        with pytest.raises(AppError) as error:
            call()
        assert error.value.code == "SERVICE_UNAVAILABLE"


# ---- 정리 명령 ----

def test_prune_command_reports_count_only(monkeypatch, capsys):
    monkeypatch.setattr(manage_audit, "execute", lambda command: 3)
    assert manage_audit.main(["prune"]) == 0
    assert json.loads(capsys.readouterr().out) == {"completed": True, "processed": 3}


def test_prune_command_without_database_fails_without_details(monkeypatch, capsys):
    monkeypatch.setattr(manage_audit, "get_settings", lambda: Settings(_env_file=None, app_env="test"))
    assert manage_audit.main(["prune"]) == 1
    assert json.loads(capsys.readouterr().out) == {"completed": False, "code": "SERVICE_UNAVAILABLE"}


def test_prune_command_hides_connection_errors(monkeypatch, capsys):
    secret = "postgresql+psycopg://user:private-password@db.invalid/app"
    monkeypatch.setattr(manage_audit, "get_settings", lambda: Settings(_env_file=None, app_env="test", database_url=secret))
    assert manage_audit.main(["prune"]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {"completed": False, "code": "SERVICE_UNAVAILABLE"} and "private-password" not in output.out + output.err


def test_prune_command_accepts_only_prune():
    with pytest.raises(SystemExit):
        manage_audit.main(["delete-all"])
