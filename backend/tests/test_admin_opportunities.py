"""운영자 공고 등록·수정 API (W07-02 · #53). 정상 입력과 공격 입력을 함께 시험한다. 모든 공고는 가상 fixture다.

완료 확인: 오래된 기준 버전의 수정은 409, 검수하지 않은 중요 변경은 공개본 추천을 보류한다.
관련 KISA 보안약점: 부적절한 인가, 크로스사이트 요청 위조, 입력 데이터 검증(개인정보·HTML 흔적), 경쟁 조건.
"""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import sessionmaker

from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.admin_opportunities.models import AdminOpportunitySearch, OpportunityCreate, OpportunityPatch
from app.modules.admin_opportunities.repository import SqlAdminOpportunityRepository
from app.modules.admin_opportunities.service import AdminOpportunityService
from app.modules.ingestion.manual import REQUIRED_QUOTES
from app.modules.opportunities.ingestion import IngestionService, RecordOpportunity
from app.modules.opportunities.ingestion_repository import SqlIngestionRepository
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.versions import OpportunitySnapshot
from app.modules.requests.service import input_fingerprint
from app.modules.sessions.service import SessionService
from app.persistence import (
    AuditEvent, ManualEvidence, OpportunityDocument as D, OpportunityPublication as P, OpportunityVersion as V,
    OpportunityWriteReceipt as R, Source, User,
)
from tests.ingestion_helpers import ingestion_database
from tests.persistence_helpers import NOW
from tests.test_contracts import opportunity
from tests.test_sessions import FakeStore, HttpAdmissionStub

URL = "https://www.50plus.or.kr/appView.do?ANN_NO=12345"
OTHER_URL = "https://www.50plus.or.kr/appView.do?ANN_NO=67890"
REQUEST_ID = "req_0123456789abcdef"
CLOCK = NOW + timedelta(minutes=1)


def content(**changes):
    return {**opportunity(), "title": "가상 운영 공고", "organization_name": "가상 기관", "source_url": URL,
            "application_url": URL, "role_tags": [], "skill_tags": [], "remote_allowed": None, "paid": None, **changes}


def create_body(**changes):
    quotes = {k: "가상 시험 근거" for k in REQUIRED_QUOTES | {"activity_region", "deadline_date"}}
    evidence = {"url": URL, "observed_at": NOW.isoformat(), "quotes": quotes, "confirmed_official": True, **changes.pop("evidence", {})}
    return {"source": "manual_50plus", "content": content(**changes.pop("content", {})), "evidence": evidence, **changes}


def prepare(engine, source):
    """가상 출처를 수동 출처로 바꾸고 운영자 계정을 만든다. 운영자 MFA 검사는 라우터 시험에서 따로 한다."""
    operator = uuid4()
    with engine.begin() as db:
        db.execute(update(Source).where(Source.id == source).values(code="manual_50plus", base_url="https://www.50plus.or.kr"))
        db.execute(insert(User), {"id": operator, "kakao_subject": "fictional-operator", "role": "admin"})
    return SqlAdminOpportunityRepository(sessionmaker(engine).begin, clock=lambda: CLOCK), operator


def create(repository, operator, body=None, key=None):
    body = OpportunityCreate.model_validate(body or create_body())
    return repository.create(operator, key or uuid4(), input_fingerprint(body.model_dump(mode="json")), body, REQUEST_ID)


def approve(engine, opportunity_id, version):
    with engine.begin() as db:
        db.execute(update(V).where(V.opportunity_id == opportunity_id, V.version == version).values(review_status="approved", reviewed_at=NOW))
        if db.scalar(select(P.version).where(P.opportunity_id == opportunity_id)) is None:
            db.execute(insert(P), {"opportunity_id": opportunity_id, "version": version})
        else:
            db.execute(update(P).where(P.opportunity_id == opportunity_id).values(version=version))


def patch(repository, operator, opportunity_id, base_version, **changes):
    return repository.update(operator, opportunity_id, OpportunityPatch(base_version=base_version, changes=changes), REQUEST_ID)


def code(call):
    with pytest.raises(AppError) as error:
        call()
    return error.value.code


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_create_records_pending_version_evidence_audit_and_replays_same_key(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        repository, operator = prepare(engine, source)
        key = uuid4()
        first = create(repository, operator, key=key)
        assert first.version == 1 and first.review_status == "pending" and first.published_version is None
        assert first.changed_fields == [] and first.important_change is False and first.published_content is None
        assert first.source.source_id == source and first.updated_at is not None
        # 같은 키·같은 입력은 새로 만들지 않고 첫 결과를 돌려준다.
        assert create(repository, operator, key=key) == first
        # 같은 키·다른 입력은 거절한다.
        assert code(lambda: create(repository, operator, create_body(content={"title": "다른 제목"}), key=key)) == "IDEMPOTENCY_KEY_REUSED"
        with engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(D)) == 1
            assert db.scalar(select(func.count()).select_from(ManualEvidence)) == 1
            audit = db.execute(select(AuditEvent.__table__)).mappings().one()
            assert (audit["actor_id"], audit["actor_role"], audit["action"], audit["target_id"], audit["result"]) == (operator, "operator", "opportunity.create", first.id, "success")
            assert audit["expires_at"] - audit["at"] == timedelta(days=30)
            receipt = db.execute(select(R.__table__)).mappings().one()
            assert receipt["expires_at"] - receipt["recorded_at"] == timedelta(hours=24)
            # 감사·재전송 기록에 공고 본문을 남기지 않는다.
            assert "가상 운영 공고" not in str(dict(audit)) + str(dict(receipt))


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_create_keeps_manual_intake_rules_and_duplicate_candidates_conflict(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        repository, operator = prepare(engine, source)
        create(repository, operator)
        # 같은 출처·URL·기관·제목·마감의 공고는 자동 병합하지 않고 409로 기존 공고 수정을 요구한다.
        assert code(lambda: create(repository, operator)) == "VERSION_CONFLICT"
        attacks = [
            create_body(content={"application_instructions": "010-1234-5678로 연락"}),  # 개인 연락처
            create_body(content={"description_text": "<script>alert(1)</script>"}),  # HTML 흔적
            create_body(content={"role_tags": ["unknown_role"]}, evidence={"quotes": {k: "근거" for k in REQUIRED_QUOTES | {"activity_region", "deadline_date", "role_tags"}}}),
            create_body(evidence={"observed_at": (NOW - timedelta(days=3)).isoformat()}),  # 48시간 넘은 확인
        ]
        # 근거 주소와 다른 비공식 원문 주소는 모델이 아니라 수동 입력 규칙에서 거절한다.
        foreign = create_body(content={"source_url": "https://evil.example/appView.do?ANN_NO=1", "application_url": "https://evil.example/appView.do?ANN_NO=1"})
        assert code(lambda: create(repository, operator, foreign)) == "VALIDATION_FAILED"
        for body in attacks:
            body["content"]["source_url"] = body["content"]["application_url"] = body["evidence"]["url"] = OTHER_URL
            assert code(lambda: create(repository, operator, body)) == "VALIDATION_FAILED"
        with engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(D)) == 1
            assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1


@pytest.mark.parametrize("body", [
    create_body(evidence={"url": "https://evil.example/appView.do?ANN_NO=1"}),
    create_body(evidence={"confirmed_official": False}),
    create_body(evidence={"quotes": {"title": "근거"}}),  # 필수 근거 누락
    create_body(source="volunteer"),  # 수집 출처를 수동 등록 출처로 쓸 수 없다
    {**create_body(), "manual_target": str(uuid4())},
])
def test_create_body_rejects_non_official_or_unevidenced_input(body):
    with pytest.raises(ValueError):
        OpportunityCreate.model_validate(body)


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_stale_patch_is_409_and_important_change_holds_published_recommendation(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        repository, operator = prepare(engine, source)
        created = create(repository, operator)
        approve(engine, created.id, 1)
        public = SqlPublicOpportunityRepository(engine.connect)
        assert [item.id for item in public.recommendation_candidates(CLOCK)] == [created.id]

        changed = patch(repository, operator, created.id, 1, deadline_date="2026-11-07")
        assert (changed.version, changed.review_status, changed.published_version) == (2, "pending", 1)
        assert changed.changed_fields == ["deadline_date"] and changed.important_change is True
        assert changed.published_content.deadline_date.isoformat() == "2026-10-31"
        # 출처를 다시 확인한 것이 아니므로 확인 시각은 기준 버전 그대로다.
        assert changed.source_checked_at == created.source_checked_at
        # 공개본은 승인 전까지 그대로이고, 중요 변경 검수 전에는 추천에서 빠진다.
        detail = public.get(created.id, CLOCK)
        assert detail.version == 1 and detail.change_pending is True
        # 추천 필터(filter_candidates)는 change_pending인 공개본을 뺀다(test_recommendation_filters).
        assert [item.change_pending for item in public.recommendation_candidates(CLOCK)] == [True]
        # 오래된 기준 버전으로는 덮어쓰지 않는다.
        assert code(lambda: patch(repository, operator, created.id, 1, title="늦은 수정")) == "VERSION_CONFLICT"
        assert code(lambda: patch(repository, operator, uuid4(), 1, title="없는 공고")) == "NOT_FOUND"
        with engine.connect() as db:
            assert db.scalar(select(func.max(V.version)).where(V.opportunity_id == created.id)) == 2
            assert db.scalars(select(AuditEvent.action).order_by(AuditEvent.at)).all() == ["opportunity.create", "opportunity.update"]


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_tag_patch_keeps_recommendation_and_collector_inherits_operator_tags(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, collector_source):
        repository, operator = prepare(engine, collector_source)
        with engine.begin() as db:
            db.execute(update(Source).where(Source.id == collector_source).values(code="fictional-ingestion", base_url="https://example.org"))
        ingestion = IngestionService(SqlIngestionRepository(engine.begin), clock=lambda: NOW + timedelta(days=1))
        snapshot = OpportunitySnapshot.model_validate({**content(), "description_truncated": False})
        first = ingestion.record(RecordOpportunity(source_id=collector_source, external_id="fictional-id", snapshot=snapshot, checked_at=NOW))
        approve(engine, first.opportunity_id, 1)

        tagged = patch(repository, operator, first.opportunity_id, 1, role_tags=["learning_mentor"], skill_tags=["학습 지도"])
        assert tagged.version == 2 and tagged.important_change is False
        assert SqlPublicOpportunityRepository(engine.connect).get(first.opportunity_id, CLOCK).change_pending is False
        approve(engine, first.opportunity_id, 2)

        # 수집기는 태그를 빈 목록으로 보낸다. 운영자 태그를 지우는 새 버전을 만들지 않는다.
        later = NOW + timedelta(hours=1)
        same = ingestion.record(RecordOpportunity(source_id=collector_source, external_id="fictional-id", snapshot=snapshot, checked_at=later))
        assert (same.version, same.outcome) == (2, "unchanged")
        moved = snapshot.model_copy(update={"schedule_text": "매주 화요일"})
        changed = ingestion.record(RecordOpportunity(source_id=collector_source, external_id="fictional-id", snapshot=moved, checked_at=later + timedelta(hours=1)))
        assert (changed.version, changed.outcome) == (3, "changed")
        with engine.connect() as db:
            tags = db.execute(select(V.role_tags, V.skill_tags).where(V.opportunity_id == first.opportunity_id, V.version == 3)).one()
        assert (list(tags[0]), list(tags[1])) == (["learning_mentor"], ["학습 지도"])


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_patch_rejects_unsafe_or_invalid_changes_without_new_version(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        repository, operator = prepare(engine, source)
        created = create(repository, operator)
        attacks = [
            {"application_instructions": "담당자 kim@example.org로 메일"},  # 개인 연락처
            {"location_text": "<img src=x onerror=alert(1)>"},  # HTML 흔적
            {"role_tags": ["unknown_role"]},  # 역할 사전에 없는 태그
            {"source_url": "https://evil.example/appView.do?ANN_NO=1"},  # 공식 상세 경로가 아닌 주소
            {"application_url": "javascript:alert(1)"},
            {"title": None},  # 필수 필드 비우기
            {"deadline_at": "2026-11-01T00:00:00Z"},  # 마감일과 다른 한국 날짜
            {"title": "가상 운영 공고"},  # 바뀐 것이 없음
        ]
        for changes in attacks:
            assert code(lambda: patch(repository, operator, created.id, 1, **changes)) == "VALIDATION_FAILED", changes
        with engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(V)) == 1
        # 설명을 직접 고치면 잘린 원문 표시도 함께 풀린다.
        edited = patch(repository, operator, created.id, 1, description_text="공식 원문 설명을 옮겼습니다.")
        assert edited.content.description_text == "공식 원문 설명을 옮겼습니다." and edited.changed_fields == []


@pytest.mark.parametrize("changes", [{}, {"unknown": 1}, {"description_truncated": True}, {"review_status": "approved"}])
def test_patch_body_accepts_only_content_fields(changes):
    with pytest.raises(ValueError):
        OpportunityPatch.model_validate({"base_version": 1, "changes": changes})
    with pytest.raises(ValueError):
        OpportunityPatch.model_validate({"base_version": "1", "changes": {"title": "x"}})


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_list_filters_literal_search_important_change_and_recent_first(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        repository, operator = prepare(engine, source)
        older = create(repository, operator)
        approve(engine, older.id, 1)
        clock = [CLOCK + timedelta(minutes=5)]
        repository.clock = lambda: clock[0]
        body = create_body(content={"title": "100%_봉사", "source_url": OTHER_URL, "application_url": OTHER_URL}, evidence={"url": OTHER_URL})
        newer = create(repository, operator, body)
        clock[0] += timedelta(minutes=5)
        held = patch(repository, operator, older.id, 1, schedule_text="매주 수요일")

        page = repository.list(AdminOpportunitySearch())
        assert [item.id for item in page.items] == [older.id, newer.id] and page.total == 2
        assert page.items[0].version == 2 and page.items[0].published_version == 1 and page.items[0].important_change
        assert page.items[0].updated_at == held.updated_at
        assert [i.id for i in repository.list(AdminOpportunitySearch(important_change=True)).items] == [older.id]
        assert [i.id for i in repository.list(AdminOpportunitySearch(important_change=False)).items] == [newer.id]
        assert [i.id for i in repository.list(AdminOpportunitySearch(q="100%_")).items] == [newer.id]
        assert [i.id for i in repository.list(AdminOpportunitySearch(q="%")).items] == [newer.id]
        assert repository.list(AdminOpportunitySearch(q="' OR 1=1 --")).total == 0
        assert repository.list(AdminOpportunitySearch(review_status="approved")).total == 0
        second = repository.list(AdminOpportunitySearch(page=2, page_size=1))
        assert [i.id for i in second.items] == [newer.id] and second.total == 2


class Operators:
    """운영자 인가 결과만 바꾸는 대역. 실제 역할·MFA 판정은 test_member_auth가 Redis+SQL로 검증한다."""

    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    async def require(self, session, *, reauth=False, operator=False):
        self.calls.append(operator)
        if isinstance(self.outcome, str):
            raise AppError(self.outcome)
        return self.outcome


class SpyRepository:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append(name)
            raise AssertionError("인가 전 저장소 호출")
        return record


def http_app(repository=None):
    app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
    app.state.session_service = SessionService(FakeStore())
    app.state.admission_service = HttpAdmissionStub()
    if repository is not None:
        app.state.admin_opportunity_service = AdminOpportunityService(repository)
    client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    client.get("/api/v1/me")  # 익명 세션과 CSRF 쿠키
    return app, client


def csrf(client, **headers):
    return {"Origin": "https://testserver", "X-CSRF-Token": client.cookies.get("__Host-rc_csrf"), **headers}


@pytest.mark.parametrize("outcome,status", [(None, 401), ("FORBIDDEN", 403), ("MFA_REQUIRED", 403), ("SESSION_EXPIRED", 401)])
def test_http_non_operators_never_reach_storage(outcome, status):
    spy = SpyRepository()
    app, client = http_app(spy)
    if outcome is not None:
        app.state.member_service = Operators(outcome)
    target = str(uuid4())
    responses = [
        client.get("/api/v1/admin/opportunities"),
        client.get(f"/api/v1/admin/opportunities/{target}"),
        client.post("/api/v1/admin/opportunities", json=create_body(), headers=csrf(client, **{"Idempotency-Key": str(uuid4())})),
        client.patch(f"/api/v1/admin/opportunities/{target}", json={"base_version": 1, "changes": {"title": "x"}}, headers=csrf(client)),
    ]
    assert [r.status_code for r in responses] == [status] * 4
    assert {r.json()["code"] for r in responses} == {outcome or "UNAUTHENTICATED"}
    assert spy.calls == []
    if outcome is not None:
        assert set(app.state.member_service.calls) == {True}


def test_http_operator_writes_require_csrf_origin_and_idempotency_key():
    spy = SpyRepository()
    app, client = http_app(spy)
    app.state.member_service = Operators(SimpleNamespace(id=uuid4()))
    target = str(uuid4())
    key = {"Idempotency-Key": str(uuid4())}
    assert client.post("/api/v1/admin/opportunities", json=create_body(), headers=key).json()["code"] == "CSRF_FAILED"
    assert client.post("/api/v1/admin/opportunities", json=create_body(), headers={**csrf(client, **key), "Origin": "https://evil.example"}).json()["code"] == "CSRF_FAILED"
    assert client.patch(f"/api/v1/admin/opportunities/{target}", json={"base_version": 1, "changes": {"title": "x"}}).json()["code"] == "CSRF_FAILED"
    assert client.post("/api/v1/admin/opportunities", json=create_body(), headers=csrf(client)).status_code == 422
    assert client.post("/api/v1/admin/opportunities", json=create_body(), headers=csrf(client, **{"Idempotency-Key": "not-a-uuid"})).status_code == 422
    assert client.patch(f"/api/v1/admin/opportunities/{target}", json={"base_version": 1, "changes": {}}, headers=csrf(client)).status_code == 422
    assert client.get("/api/v1/admin/opportunities", params={"page_size": 21}).status_code == 422
    assert client.get("/api/v1/admin/opportunities", params={"role": "admin"}).status_code == 422
    assert spy.calls == []


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_http_operator_round_trip_on_real_database(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        repository, operator = prepare(engine, source)
        repository.clock = lambda: CLOCK
        app, client = http_app(repository)
        app.state.member_service = Operators(SimpleNamespace(id=operator))
        key = str(uuid4())
        created = client.post("/api/v1/admin/opportunities", json=create_body(), headers=csrf(client, **{"Idempotency-Key": key}))
        assert created.status_code == 201 and created.headers["cache-control"] == "no-store"
        body = created.json()
        assert body["version"] == 1 and body["review_status"] == "pending" and body["content"]["title"] == "가상 운영 공고"
        replay = client.post("/api/v1/admin/opportunities", json=create_body(), headers=csrf(client, **{"Idempotency-Key": key}))
        assert replay.status_code == 201 and replay.json() == body
        reused = client.post("/api/v1/admin/opportunities", json=create_body(content={"title": "다른 제목"}), headers=csrf(client, **{"Idempotency-Key": key}))
        assert reused.status_code == 409 and reused.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

        path = f"/api/v1/admin/opportunities/{body['id']}"
        detail = client.get(path)
        assert detail.status_code == 200 and detail.headers["cache-control"] == "no-store" and detail.json() == body
        updated = client.patch(path, json={"base_version": 1, "changes": {"skill_tags": ["낭독"]}}, headers=csrf(client))
        assert updated.status_code == 200 and updated.json()["version"] == 2 and updated.json()["content"]["skill_tags"] == ["낭독"]
        stale = client.patch(path, json={"base_version": 1, "changes": {"title": "늦은 수정"}}, headers=csrf(client))
        assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
        listing = client.get("/api/v1/admin/opportunities", params={"review_status": "pending"})
        assert listing.status_code == 200 and [item["id"] for item in listing.json()["items"]] == [body["id"]]
        assert client.get(f"/api/v1/admin/opportunities/{uuid4()}").status_code == 404
        with engine.connect() as db:
            assert db.scalars(select(AuditEvent.request_id)).all() and all(rid.startswith("req_") for rid in db.scalars(select(AuditEvent.request_id)))


def test_contract_examples_match_backend_models():
    from pathlib import Path
    import json
    # PyYAML은 백엔드 의존성이 아니다. 백엔드 단위 잡(bandit이 설치)에서만 돌고, 해시 고정 통합 잡에서는 건너뛴다.
    yaml = pytest.importorskip("yaml")
    from app.modules.admin_opportunities.models import AdminOpportunity
    from app.modules.ingestion.manual import ManualInput
    spec = yaml.safe_load((Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml").read_text(encoding="utf-8"))
    post = spec["paths"]["/admin/opportunities"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    body = OpportunityCreate.model_validate(post["manual"]["value"])
    ManualInput(source_id=uuid4(), snapshot=OpportunitySnapshot.model_validate({**body.content.model_dump(), "description_truncated": False}), evidence=body.evidence)
    with pytest.raises(ValueError):
        OpportunityCreate.model_validate(post["unlistedUrl"]["value"])
    item = spec["paths"]["/admin/opportunities/{opportunity_id}"]
    examples = item["patch"]["requestBody"]["content"]["application/json"]["examples"]
    OpportunityPatch.model_validate(examples["deadline"]["value"])
    with pytest.raises(ValueError):
        OpportunityPatch.model_validate(examples["empty"]["value"])
    AdminOpportunity.model_validate_json(json.dumps(item["get"]["responses"]["200"]["content"]["application/json"]["examples"]["importantChange"]["value"]))
