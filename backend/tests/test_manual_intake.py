"""수동 입력 정상/공격 경계. 모든 내용은 가상 fixture이며 실제 공고로 집계하지 않는다."""

from contextlib import contextmanager
from datetime import timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.collect import store_factory
from app.core.business_errors import AppError
from app.modules.ingestion.manual import ManualInput, ManualIntake, REQUIRED_QUOTES, official_url, read_input
from app.persistence import ManualEvidence as E, OpportunityDocument as D, OpportunityVersion as V, OpportunityPublication as P, Source
from tests.ingestion_helpers import ingestion_database
from tests.persistence_helpers import NOW
from tests.test_contracts import opportunity, requirement

URL = "https://www.50plus.or.kr/appView.do?ANN_NO=12345"


def material(source, **changes):
    snapshot = {**opportunity(), "title": "가상 공고", "organization_name": "가상 기관", "source_url": URL,
                "application_url": URL, "description_truncated": False, "role_tags": [], "skill_tags": [],
                "remote_allowed": None, "paid": None, **changes.pop("snapshot", {})}
    quotes = {k: "가상 시험 근거" for k in REQUIRED_QUOTES | {"activity_region", "deadline_date"}}
    return {"source_id": str(source), "snapshot": snapshot, "evidence": {"url": URL,
        "observed_at": NOW.isoformat(), "quotes": quotes, "confirmed_official": True}, **changes}


def setup(engine, source):
    with engine.begin() as db:
        db.execute(update(Source).where(Source.id == source).values(code="manual_50plus", base_url="https://www.50plus.or.kr"))
    return ManualIntake(sessionmaker(engine).begin, store_factory, clock=lambda: NOW + timedelta(minutes=1))


@pytest.mark.parametrize("url", [
    "https://evil.example/nwc/detail.do?id=12345", "https://www.50plus.or.kr.evil.example/nwc/detail.do?id=12345",
    "https://www.50plus.or.kr@evil.example/nwc/detail.do?id=12345", "https://127.0.0.1/nwc/detail.do?id=12345",
    URL + "&url=https://evil.example", URL + "&ANN_NO=999", URL.replace("12345", "%31%32%33%34%35%26x%3D1"),
    URL.replace("/appView", "/../appView"), URL.replace("/appView", "/%61ppView"), URL.replace("https", "http"),
    URL + "#fragment", URL.replace(".or.kr/", ".or.kr:443/"), URL.replace("12345", ""),
    "https://www.50plus.or.kr/nwc/detail.do?id=12345",
    URL.replace("ANN_NO", "id"), URL.replace("12345", "0"), URL.replace("12345", "-1"),
    URL.replace("12345", "1234567890123"), URL.replace("ANN_NO", "ann_no"),
])
def test_official_path_rejects_host_confusion_redirect_and_ambiguous_identifiers(url):
    data = material(uuid4()); data["snapshot"]["source_url"] = data["evidence"]["url"] = url
    with pytest.raises((ValidationError, ValueError)):
        ManualInput.model_validate(data)


@pytest.mark.parametrize("path", ["appView.do", "in_appView.do"])
def test_verified_50plus_job_paths_accept_only_announcement_id(path):
    url = "https://www.50plus.or.kr/" + path + "?ANN_NO=12345"
    assert official_url(url) == url
    data = material(uuid4(), snapshot={"source_url": url, "application_url": url})
    data["evidence"]["url"] = url
    assert ManualInput.model_validate(data).snapshot.source_url == url


def test_verified_work24_path_and_query_order():
    a = "https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?wantedAuthNo=K123&infoTypeGroup=tb_workinfoworknet&infoTypeCd=VALIDATION"
    b = "https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?infoTypeCd=VALIDATION&infoTypeGroup=tb_workinfoworknet&wantedAuthNo=K123"
    assert official_url(a) == b


@pytest.mark.parametrize("field,value", [("review_status", "approved"), ("version", 9), ("external_id", "x"), ("confirmed_at", NOW.isoformat())])
def test_no_input_can_approve_or_set_identity(field, value):
    data = material(uuid4()); data[field] = value
    with pytest.raises(ValidationError):
        ManualInput.model_validate(data)


@pytest.mark.parametrize("value", [False, 1, "true"])
def test_evidence_attestation_is_required_strict_boolean(value):
    data = material(uuid4());data["evidence"]["confirmed_official"] = value
    with pytest.raises(ValidationError):
        ManualInput.model_validate(data)


def test_missing_field_evidence_contacts_html_and_nested_requirement_are_rejected():
    data = material(uuid4()); del data["evidence"]["quotes"]["requirements"]
    with pytest.raises(ValidationError):ManualInput.model_validate(data)
    for value in ("<script>payload</script>", "person@example.invalid", "010-0000-0000"):
        data = material(uuid4()); data["evidence"]["quotes"]["title"] = value
        with pytest.raises(ValidationError):ManualInput.model_validate(data)
        data = material(uuid4(), snapshot={"requirements": [requirement(source_evidence=value)]})
        with pytest.raises(ValidationError):ManualInput.model_validate(data)
    data = material(uuid4(), snapshot={"hours_per_week": 10.0})
    with pytest.raises(ValidationError):ManualInput.model_validate(data)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'[' * 25 + b']' * 25, b' ' * 65537, b'\xff', b'{"source_id":'],
                         ids=["duplicate-key", "nan", "depth", "size", "encoding", "malformed"])
def test_bounded_strict_json(raw):
    with pytest.raises((ValueError, ValidationError)):
        read_input(io.BytesIO(raw))


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_atomic_pending_evidence_replay_versions_and_publication(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        service = setup(engine, source); data = material(source)
        parsed = read_input(io.BytesIO(json.dumps(data).encode()))
        assert "가상 공고" not in repr(parsed) and "가상 시험 근거" not in repr(parsed.evidence)
        result = service.record(parsed)
        with engine.connect() as db:
            assert db.scalar(select(V.review_status)) == "pending"
            assert db.scalar(select(func.count()).select_from(P)) == 0
            assert db.scalar(select(func.count()).select_from(E)) == 1
        with pytest.raises(AppError, match="VERSION_CONFLICT"):
            service.record(parsed)
        data["manual_target"] = str(result.opportunity_id)
        replay = service.record(ManualInput.model_validate(data)); assert replay.outcome == "unchanged"
        with engine.connect() as db: assert db.scalar(select(func.count()).select_from(E)) == 1
        data["snapshot"]["schedule_text"] = "가상 변경 일정"
        data["evidence"]["quotes"]["schedule_text"] = "가상 변경 일정"
        data["evidence"]["observed_at"] = (NOW + timedelta(seconds=1)).isoformat()
        changed = service.record(ManualInput.model_validate(data));assert changed.version == 2
        with engine.begin() as db:
            assert db.scalar(select(func.count()).select_from(E)) == 2
            with pytest.raises(IntegrityError), db.begin_nested():db.execute(update(E).values(quotes={}))
        assert service.progress()["current_candidates"] == 1
        assert service.progress()["current_approved"] == 0


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_evidence_insert_failure_rolls_back_created_document(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        setup(engine, source)
        @contextmanager
        def failing_transaction():
            with sessionmaker(engine).begin() as db:
                execute = db.execute
                def fail(statement, *args, **kwargs):
                    if getattr(statement, "is_insert", False) and statement.table.name == "manual_evidence":
                        raise RuntimeError("가상 근거 저장 실패")
                    return execute(statement, *args, **kwargs)
                db.execute = fail
                yield db
        service = ManualIntake(failing_transaction, store_factory, clock=lambda: NOW + timedelta(minutes=1))
        with pytest.raises(RuntimeError):service.record(ManualInput.model_validate(material(source)))
        with engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(D)) == 0
            assert db.scalar(select(func.count()).select_from(V)) == 0


@pytest.mark.parametrize("offset", [timedelta(seconds=61), -timedelta(hours=49)])
def test_future_and_old_evidence_never_writes(offset, tmp_path):
    with ingestion_database("sqlite", tmp_path) as (engine, source):
        service = setup(engine, source);data = material(source)
        data["evidence"]["observed_at"] = (NOW + offset).isoformat()
        with pytest.raises(AppError):service.record(ManualInput.model_validate(data))
        with engine.connect() as db:assert db.scalar(select(func.count()).select_from(D)) == 0


def test_progress_does_not_count_closed_unknown_stale_unresolved_or_duplicates(tmp_path):
    with ingestion_database("sqlite", tmp_path) as (engine, source):
        service = setup(engine, source)
        for index, changes in enumerate([{}, {}, {"recruitment_status": "closed"}, {"recruitment_status": "unknown"},
                {"requirements": [requirement(field="other", operator=None, value=None, clarity="needs_review")]},
                {"activity_region": None}, {"description_truncated": True}]):
            url = URL.replace("12345", str(1000 + index)); data = material(source, snapshot=changes)
            data["snapshot"]["source_url"] = data["snapshot"]["application_url"] = data["evidence"]["url"] = url
            service.record(ManualInput.model_validate(data))
        progress = service.progress()
        assert progress == {"target": 20, "recorded_documents": 7, "current_candidates": 1,
            "current_approved": 0, "held_or_duplicate": 6, "candidate_shortfall": 19, "approved_shortfall": 20}
        service.clock = lambda: NOW + timedelta(hours=49)
        assert service.progress()["current_candidates"] == 0


@pytest.mark.parametrize("change", ["disabled", "wrong_base", "wrong_code", "wrong_host", "unknown_role"])
def test_source_and_dictionary_boundary_before_write(change, tmp_path):
    with ingestion_database("sqlite", tmp_path) as (engine, source):
        service = setup(engine, source);data = material(source)
        values = {"disabled": {"enabled": False}, "wrong_base": {"base_url": "https://evil.example"},
                  "wrong_code": {"code": "senuri"}}.get(change, {})
        with engine.begin() as db:
            if values:db.execute(update(Source).where(Source.id == source).values(**values))
        if change == "wrong_host":
            url = "https://www.1365.go.kr/vols/P9210/partcptn/timeCptn.do?type=show&progrmRegistNo=12345"
            data["snapshot"]["source_url"] = data["snapshot"]["application_url"] = data["evidence"]["url"] = url
        if change == "unknown_role":
            data["snapshot"]["role_tags"] = ["unknown_role"]
            data["evidence"]["quotes"]["role_tags"] = "가상 역할"
        with pytest.raises(AppError):service.record(ManualInput.model_validate(data))
        with engine.connect() as db:assert db.scalar(select(func.count()).select_from(D)) == 0


def test_twenty_fixture_candidates_do_not_implicitly_approve_or_publish(tmp_path):
    with ingestion_database("sqlite", tmp_path) as (engine, source):
        service = setup(engine, source)
        for index in range(20):
            url = URL.replace("12345", str(3000 + index))
            data = material(source, snapshot={"title": f"가상 공고 {index}"})
            data["snapshot"]["source_url"] = data["snapshot"]["application_url"] = data["evidence"]["url"] = url
            service.record(ManualInput.model_validate(data))
        counts = service.progress()
        assert counts["current_candidates"] == 20 and counts["candidate_shortfall"] == 0
        assert counts["current_approved"] == 0 and counts["approved_shortfall"] == 20
        with engine.begin() as db:
            first = db.execute(select(V.opportunity_id, V.version).limit(1)).one()
            db.execute(update(V).where(V.opportunity_id == first.opportunity_id).values(review_status="approved", reviewed_at=NOW))
        assert service.progress()["current_approved"] == 1
        with engine.connect() as db:assert db.scalar(select(func.count()).select_from(P)) == 0


def test_cli_validation_does_not_echo_input_or_need_database():
    data = json.dumps(material(uuid4()))
    env = {**os.environ, "DATABASE_URL": "invalid"}
    result = subprocess.run([sys.executable, "-m", "app.manual_intake", "--validate"], input=data,
        text=True, capture_output=True, timeout=10, env=env, cwd=Path(__file__).resolve().parents[1])
    assert result.returncode == 0 and json.loads(result.stdout)["status"] == "format_valid"
    assert "가상 공고" not in result.stdout + result.stderr
    result = subprocess.run([sys.executable, "-m", "app.manual_intake", "--record"], input=data[:-1],
        text=True, capture_output=True, timeout=10, env=env, cwd=Path(__file__).resolve().parents[1])
    assert result.returncode == 1 and result.stdout.strip() == '{"status":"rejected"}'
    assert result.stderr == ""
