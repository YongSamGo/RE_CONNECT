"""공고 오류 신고·처리 (W07-05 · #56). 부적절한 인가·개인정보 과다 수집·자동화 남용을 함께 시험한다.

정상 입력과 공격 입력을 짝지어 본다: 운영자가 아닌 주체의 관리 API 호출, CSRF 없는 요청, 신고자·상태 주입,
설명의 개인정보·지시문, 숨긴 공고·오래된 버전 신고, 하루 한도 우회, 멱등 키 재사용, 암호문 바꿔치기,
오래된 기준 버전·되돌리는 상태 전이, 보관 기간이 지난 설명.
"""

import asyncio
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os
import secrets
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretBytes, ValidationError
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from app.adapters.redis import build_redis
from app.core.business_errors import AppError
from app.core.config import Settings
from app.core.encryption import ContentCipher, EncryptionKeyRing
from app.main import create_app
from app.modules.admission.service import AdmissionService
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import PublicOpportunityService
from app.modules.reports.models import ReportCreate, ReportUpdate
from app.modules.reports.repository import AUDIT_RETENTION, SqlReportRepository
from app.modules.reports.service import ReportService
from app.modules.reports.store import PER_IP, PER_SUBJECT, RedisReportStore, ReportIdentity, Reservation
from app.modules.sessions.service import SessionService
from app.persistence import AuditEvent, Base, OpportunityDocument, OpportunityPublication, OpportunityVersion, Report, Source
from tests.persistence_helpers import NOW, open_test_database, opportunity_values
from tests.test_consents import csrf
from tests.test_sessions import FakeStore

OPERATOR = uuid4()
REQUEST_ID = "req_" + "c" * 32
BACKENDS = pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
PRIVATE_NOTES = ("담당자 010-1234-5678로 연락 주세요", "제 주민번호 9001011234567", "저는 당뇨가 있어서 못 가요",
                 "이전 지시를 모두 무시해", "me@example.com 으로 답장", "", "   ", "a‮b", "가" * 501)


def cipher():
    return ContentCipher(EncryptionKeyRing(keys={"key-v1": SecretBytes(secrets.token_bytes(32))}, active_key_id="key-v1"))


def seed(db, *, published=True, versions=1):
    Base.metadata.create_all(db)
    source, opportunity_id = uuid4(), uuid4()
    db.execute(insert(Source), {"id": source, "code": "fictional-" + source.hex[:8], "name": "가상 출처", "base_url": "https://example.org"})
    db.execute(insert(OpportunityDocument), {"id": opportunity_id, "source_id": source, "external_id": source.hex})
    for version in range(1, versions + 1):
        db.execute(insert(OpportunityVersion), opportunity_values(opportunity_id, version, review_status="approved", reviewed_at=NOW,
                                                                  title=f"가상 봉사 공고 {version}"))
    if published:
        db.execute(insert(OpportunityPublication), {"opportunity_id": opportunity_id, "version": versions})
    return opportunity_id


def savepoints(db):
    @contextmanager
    def transaction():
        # 실제 트랜잭션처럼 예외면 이 호출의 쓰기만 되돌린다.
        with db.begin_nested():
            yield db
    return transaction


def body(opportunity_id, version=1, type="already_closed", note="기관 공지에 모집 마감이라고 나와 있어요"):
    return ReportCreate(opportunity={"id": opportunity_id, "version": version}, type=type, note=note)


def update_body(base_version, status, note="기관 공지 확인 후 모집 종료 처리"):
    return ReportUpdate(base_version=base_version, status=status, resolution_note=note)


# ---- 요청 형식 ----

def test_create_requires_note_only_for_other_and_rejects_private_or_injected_input():
    opportunity_id = uuid4()
    assert body(opportunity_id, note=None).note is None
    assert body(opportunity_id, type="other", note="공고 사진이 다른 기관 것이에요").type == "other"
    with pytest.raises(ValidationError) as error:
        body(opportunity_id, type="other", note=None)
    assert [(e["loc"], e["type"]) for e in error.value.errors()] == [(("note",), "required_with")]
    for note in PRIVATE_NOTES:
        with pytest.raises(ValidationError):
            body(opportunity_id, note=note)
    for injected in ({"reporter_id": str(uuid4())}, {"status": "resolved"}, {"ip": "192.0.2.1"}, {"contact": "010"}):
        with pytest.raises(ValidationError):
            ReportCreate.model_validate({"opportunity": {"id": str(opportunity_id), "version": 1}, "type": "broken_link", "note": None, **injected})
    for version in (0, -1, "1", 1.0, True):
        with pytest.raises(ValidationError):
            ReportCreate.model_validate({"opportunity": {"id": str(opportunity_id), "version": version}, "type": "broken_link", "note": None})
    with pytest.raises(ValidationError):
        ReportCreate.model_validate({"opportunity": {"id": str(opportunity_id), "version": 1}, "type": "spam", "note": None})


def test_update_requires_reason_to_close_and_never_accepts_received_or_private_reason():
    assert update_body(1, "in_progress", None).resolution_note is None
    for status in ("resolved", "dismissed"):
        with pytest.raises(ValidationError) as error:
            update_body(2, status, None)
        assert error.value.errors()[0]["type"] == "required_with"
    with pytest.raises(ValidationError):
        update_body(1, "received", None)
    for note in PRIVATE_NOTES:
        with pytest.raises(ValidationError):
            update_body(2, "resolved", note)
    with pytest.raises(ValidationError):
        ReportUpdate.model_validate({"base_version": 1, "status": "in_progress", "resolution_note": None, "actor_id": str(uuid4())})


# ---- 저장·처리 (실제 DB) ----

@BACKENDS
def test_note_is_stored_only_encrypted_and_create_is_idempotent(backend):
    with open_test_database(backend) as db:
        opportunity_id = seed(db)
        repository = SqlReportRepository(savepoints(db), cipher())
        report_id = uuid4()
        repository.create(report_id, NOW, body(opportunity_id))
        repository.create(report_id, NOW, body(opportunity_id))
        rows = db.execute(select(Report.__table__)).mappings().all()
        assert len(rows) == 1 and rows[0]["status"] == "received" and rows[0]["version"] == 1
        assert "모집 마감".encode() not in bytes(rows[0]["details_ciphertext"])
        assert rows[0]["resolution_ciphertext"] is None and rows[0]["purged_at"] is None
        listed = repository.listing(None, 1, 20)
        assert listed.total == 1 and listed.items[0].note == "기관 공지에 모집 마감이라고 나와 있어요"
        assert listed.items[0].opportunity_title == "가상 봉사 공고 1" and listed.items[0].created_at == NOW


@BACKENDS
def test_listing_filters_status_pages_oldest_first(backend):
    with open_test_database(backend) as db:
        opportunity_id = seed(db)
        repository = SqlReportRepository(savepoints(db), cipher())
        ids = [uuid4() for _ in range(23)]
        for minutes, report_id in enumerate(ids):
            repository.create(report_id, NOW + timedelta(minutes=minutes), body(opportunity_id, type="broken_link", note=None))
        repository.update(ids[0], update_body(1, "in_progress", None), actor_id=OPERATOR, request_id=REQUEST_ID, at=NOW + timedelta(hours=1))
        first, last = repository.listing(None, 1, 20), repository.listing(None, 2, 20)
        assert [item.report_id for item in first.items + last.items] == ids and first.total == 23
        received = repository.listing("received", 1, 20)
        assert received.total == 22 and ids[0] not in [item.report_id for item in received.items]
        assert repository.listing("in_progress", 1, 20).items[0].report_id == ids[0]
        assert repository.listing(None, 9, 20).items == []


@BACKENDS
def test_update_moves_forward_once_and_records_minimal_audit(backend):
    with open_test_database(backend) as db:
        opportunity_id = seed(db)
        repository = SqlReportRepository(savepoints(db), cipher())
        report_id = uuid4()
        repository.create(report_id, NOW, body(opportunity_id))
        started = repository.update(report_id, update_body(1, "in_progress", None), actor_id=OPERATOR, request_id=REQUEST_ID, at=NOW + timedelta(minutes=5))
        assert (started.status, started.version, started.resolution_note, started.updated_at) == ("in_progress", 2, None, NOW + timedelta(minutes=5))
        closed = repository.update(report_id, update_body(2, "resolved"), actor_id=OPERATOR, request_id=REQUEST_ID, at=NOW + timedelta(minutes=9))
        assert (closed.status, closed.version, closed.resolution_note) == ("resolved", 3, "기관 공지 확인 후 모집 종료 처리")
        assert repository.listing(None, 1, 20).items[0] == closed
        stored = db.execute(select(Report.resolution_ciphertext)).scalar_one()
        assert "모집 종료".encode() not in bytes(stored)
        audits = db.execute(select(AuditEvent.__table__).order_by(AuditEvent.at)).mappings().all()
        assert [(a["actor_id"], a["actor_role"], a["action"], a["target_type"], a["target_id"], a["result"], a["request_id"]) for a in audits] == [
            (OPERATOR, "operator", "report.update", "report", report_id, "success", REQUEST_ID)] * 2
        assert audits[1]["expires_at"] - audits[1]["at"] == AUDIT_RETENTION


@BACKENDS
@pytest.mark.parametrize(("steps", "attempt", "code"), [
    ([], (1, "resolved"), "INVALID_STATE_TRANSITION"),
    ([], (1, "dismissed"), "INVALID_STATE_TRANSITION"),
    ([(1, "in_progress")], (2, "in_progress"), "INVALID_STATE_TRANSITION"),
    ([(1, "in_progress"), (2, "dismissed")], (3, "in_progress"), "INVALID_STATE_TRANSITION"),
    ([(1, "in_progress"), (2, "resolved")], (3, "dismissed"), "INVALID_STATE_TRANSITION"),
    ([(1, "in_progress")], (1, "resolved"), "VERSION_CONFLICT"),
    ([], (2, "in_progress"), "VERSION_CONFLICT"),
])
def test_stale_or_backward_transition_changes_nothing(backend, steps, attempt, code):
    with open_test_database(backend) as db:
        opportunity_id = seed(db)
        repository = SqlReportRepository(savepoints(db), cipher())
        report_id = uuid4()
        repository.create(report_id, NOW, body(opportunity_id))
        for version, status in steps:
            repository.update(report_id, update_body(version, status), actor_id=OPERATOR, request_id=REQUEST_ID, at=NOW)
        before = dict(db.execute(select(Report.__table__)).mappings().one())
        audits = db.execute(select(AuditEvent.id)).all()
        with pytest.raises(AppError) as error:
            repository.update(report_id, update_body(*attempt), actor_id=OPERATOR, request_id=REQUEST_ID, at=NOW)
        assert error.value.code == code
        assert dict(db.execute(select(Report.__table__)).mappings().one()) == before
        assert db.execute(select(AuditEvent.id)).all() == audits


@BACKENDS
def test_unknown_report_is_not_found_and_failed_audit_rolls_back_update(backend):
    with open_test_database(backend) as db:
        opportunity_id = seed(db)
        repository = SqlReportRepository(savepoints(db), cipher())
        with pytest.raises(AppError) as error:
            repository.update(uuid4(), update_body(1, "in_progress"), actor_id=OPERATOR, request_id=REQUEST_ID, at=NOW)
        assert error.value.code == "NOT_FOUND"
        report_id = uuid4()
        repository.create(report_id, NOW, body(opportunity_id))
        # 감사 기록 제약 위반(짧은 요청 ID)이면 상태 변경도 남지 않는다.
        with pytest.raises(AppError) as error:
            repository.update(report_id, update_body(1, "in_progress"), actor_id=OPERATOR, request_id="short", at=NOW)
        assert error.value.code == "SERVICE_UNAVAILABLE"
        assert db.execute(select(Report.status, Report.version)).one() == ("received", 1)
        assert db.execute(select(AuditEvent.id)).all() == []


@BACKENDS
def test_swapped_or_foreign_ciphertext_is_not_shown(backend):
    with open_test_database(backend) as db:
        opportunity_id = seed(db)
        repository = SqlReportRepository(savepoints(db), cipher())
        first, second = uuid4(), uuid4()
        repository.create(first, NOW, body(opportunity_id, note="첫 번째 신고 설명"))
        repository.create(second, NOW, body(opportunity_id, note="두 번째 신고 설명"))
        stolen = db.execute(select(Report.details_ciphertext, Report.details_nonce, Report.details_key_id).where(Report.id == second)).one()
        db.execute(update(Report).where(Report.id == first).values(details_ciphertext=stolen[0], details_nonce=stolen[1], details_key_id=stolen[2]))
        with pytest.raises(AppError) as error:
            repository.listing(None, 1, 20)
        assert error.value.code == "SERVICE_UNAVAILABLE"
        with pytest.raises(AppError):
            SqlReportRepository(savepoints(db), None).listing(None, 1, 20)


@BACKENDS
def test_purge_clears_text_thirty_days_after_closing_and_keeps_quality_record(backend):
    with open_test_database(backend) as db:
        opportunity_id = seed(db)
        repository = SqlReportRepository(savepoints(db), cipher())
        old, recent, open_report = uuid4(), uuid4(), uuid4()
        for report_id in (old, recent, open_report):
            repository.create(report_id, NOW, body(opportunity_id, type="other", note="공고 사진이 다른 기관 것이에요"))
            repository.update(report_id, update_body(1, "in_progress"), actor_id=OPERATOR, request_id=REQUEST_ID, at=NOW)
        repository.update(old, update_body(2, "dismissed"), actor_id=OPERATOR, request_id=REQUEST_ID, at=NOW)
        repository.update(recent, update_body(2, "resolved"), actor_id=OPERATOR, request_id=REQUEST_ID, at=NOW + timedelta(days=5))
        assert repository.purge(NOW + timedelta(days=30) - timedelta(seconds=1), 100) == 0
        assert repository.purge(NOW + timedelta(days=31), 100) == 1
        assert repository.purge(NOW + timedelta(days=31), 100) == 0
        rows = {row["id"]: row for row in db.execute(select(Report.__table__)).mappings()}
        assert rows[old]["details_ciphertext"] is None and rows[old]["resolution_ciphertext"] is None
        assert (rows[old]["type"], rows[old]["status"], rows[old]["opportunity_version"], rows[old]["purged_at"]) == ("other", "dismissed", 1, NOW + timedelta(days=31))
        assert rows[recent]["details_ciphertext"] is not None and rows[open_report]["details_ciphertext"] is not None
        purged = next(item for item in repository.listing(None, 1, 20).items if item.report_id == old)
        assert (purged.note, purged.resolution_note, purged.status) == (None, None, "dismissed")


@BACKENDS
@pytest.mark.parametrize("changes", [
    {"status": "resolved"},
    {"resolution_ciphertext": b"x" * 32, "resolution_nonce": b"n" * 12, "resolution_key_id": "key-v1"},
    {"status": "in_progress", "purged_at": NOW},
    {"status": "in_progress", "resolution_ciphertext": b"x" * 32},
    {"updated_at": NOW - timedelta(seconds=1)},
    {"type": "other"},
])
def test_database_rejects_inconsistent_report_rows(backend, changes):
    with open_test_database(backend) as db:
        opportunity_id = seed(db)
        values = {"id": uuid4(), "opportunity_id": opportunity_id, "opportunity_version": 1, "type": "broken_link",
                  "status": "received", "version": 1, "received_at": NOW, "updated_at": NOW}
        db.execute(insert(Report), values | {"id": uuid4()})
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(insert(Report), values | changes)


# ---- 접수 순서 (가짜 한도 저장소) ----

class MemoryStore:
    """멱등 기록·한도 판정만 흉내 낸다. 원자성과 실제 한도 수치는 실제 Redis 시험이 본다."""

    def __init__(self, limit=10):
        self.records, self.counts, self.calls, self.limit = {}, {}, [], limit

    async def reserve(self, identity, key_id, input_hash, report_id, *, peek):
        self.calls.append(peek)
        record = self.records.get((identity.subject, key_id))
        if record is not None:
            if record[0] != input_hash:
                raise AppError("IDEMPOTENCY_KEY_REUSED")
            return Reservation(record[1], record[2], True)
        if peek:
            return None
        if self.counts.get(identity.subject_opportunity, 0) >= 1 or self.counts.get(identity.ip, 0) >= self.limit:
            raise AppError("DAILY_QUOTA_EXCEEDED", retry_after=60)
        for name in (identity.subject_opportunity, identity.ip):
            self.counts[name] = self.counts.get(name, 0) + 1
        self.records[(identity.subject, key_id)] = (input_hash, report_id, NOW)
        return Reservation(report_id, NOW, False)


def digest(category, value):
    import hashlib
    return hashlib.sha256(f"{category}:{value}".encode()).hexdigest()


def service_for(db, store=None, repository=None):
    opportunities = PublicOpportunityService(SqlPublicOpportunityRepository(lambda: nullcontext(db)))
    return ReportService(store or MemoryStore(), repository or SqlReportRepository(savepoints(db), cipher()), opportunities, digest, clock=lambda: NOW)


def test_hidden_or_stale_opportunity_is_rejected_without_using_quota():
    with open_test_database("sqlite") as db:
        hidden = seed(db, published=False)
        changed = seed(db, versions=2)
        store = MemoryStore()
        service = service_for(db, store)
        subject = uuid4()
        for target, version, code in ((hidden, 1, "NOT_FOUND"), (uuid4(), 1, "NOT_FOUND"), (changed, 1, "VERSION_CONFLICT")):
            with pytest.raises(AppError) as error:
                asyncio.run(service.create(subject, "192.0.2.1", str(uuid4()), body(target, version)))
            assert error.value.code == code
        assert store.counts == {} and set(store.calls) == {True}
        receipt = asyncio.run(service.create(subject, "192.0.2.1", str(uuid4()), body(changed, 2)))
        assert db.execute(select(Report.opportunity_version)).scalar_one() == 2 and receipt.received_at == NOW


def test_same_key_replays_first_receipt_and_changed_body_is_refused():
    with open_test_database("sqlite") as db:
        opportunity_id = seed(db)
        service = service_for(db)
        subject, key = uuid4(), str(uuid4())
        first = asyncio.run(service.create(subject, "192.0.2.1", key, body(opportunity_id)))
        # 첫 접수 뒤 공고가 내려가도 같은 요청의 재전송은 첫 결과를 돌려준다.
        db.execute(OpportunityPublication.__table__.delete())
        assert asyncio.run(service.create(subject, "192.0.2.1", key, body(opportunity_id))) == first
        with pytest.raises(AppError) as error:
            asyncio.run(service.create(subject, "192.0.2.1", key, body(opportunity_id, note="설명을 바꿔서 다시 보냄")))
        assert error.value.code == "IDEMPOTENCY_KEY_REUSED"
        for bad in ("not-a-uuid", uuid4().hex, ""):
            with pytest.raises(AppError) as error:
                asyncio.run(service.create(subject, "192.0.2.1", bad, body(opportunity_id)))
            assert error.value.code == "VALIDATION_FAILED"
        assert len(db.execute(select(Report.id)).all()) == 1


class FlakyRepository(SqlReportRepository):
    def __init__(self, *args):
        super().__init__(*args)
        self.fail = True

    def create(self, *args):
        if self.fail:
            self.fail = False
            raise AppError("SERVICE_UNAVAILABLE")
        return super().create(*args)


def test_lost_write_is_completed_by_retry_with_the_same_report_id():
    with open_test_database("sqlite") as db:
        opportunity_id = seed(db)
        store = MemoryStore()
        service = service_for(db, store, FlakyRepository(savepoints(db), cipher()))
        subject, key = uuid4(), str(uuid4())
        with pytest.raises(AppError):
            asyncio.run(service.create(subject, "192.0.2.1", key, body(opportunity_id)))
        reserved = next(iter(store.records.values()))[1]
        receipt = asyncio.run(service.create(subject, "192.0.2.1", key, body(opportunity_id)))
        assert receipt.report_id == reserved and db.execute(select(Report.id)).scalar_one() == reserved
        # 같은 공고 하루 1건 한도: 새 키로 다시 신고하면 막힌다.
        with pytest.raises(AppError) as error:
            asyncio.run(service.create(subject, "192.0.2.1", str(uuid4()), body(opportunity_id, type="broken_link", note=None)))
        assert error.value.code == "DAILY_QUOTA_EXCEEDED"


# ---- 실제 Redis 한도 ----

def with_redis(scenario):
    url = os.environ.get("PERSISTENCE_TEST_REDIS_URL")
    if not url:
        pytest.skip("신고 한도는 CI의 실제 Redis에서 검증")

    async def run():
        client = build_redis(Settings(_env_file=None, redis_url=url))
        store = RedisReportStore(client, prefix=f"test:report:{uuid4().hex}:")
        try:
            await scenario(store, client)
        finally:
            keys = [key async for key in client.scan_iter(match=store.prefix + "*")]
            if keys:
                await client.delete(*keys)
            await client.aclose()
    asyncio.run(run())


def identity(subject="s", ip="i", opportunity=None):
    return ReportIdentity(subject=digest("s", subject), ip=digest("i", ip), subject_opportunity=digest("o", f"{subject}:{opportunity or uuid4()}"))


def test_redis_receipt_replays_and_peek_never_counts():
    async def scenario(store, client):
        who, key, report_id = identity(), uuid4(), uuid4()
        assert await store.reserve(who, key, "a" * 64, uuid4(), peek=True) is None
        assert await client.exists(store.limits_key) == 0
        first = await store.reserve(who, key, "a" * 64, report_id, peek=False)
        assert (first.report_id, first.replay) == (report_id, False)
        again = await store.reserve(who, key, "a" * 64, uuid4(), peek=False)
        assert (again.report_id, again.received_at, again.replay) == (report_id, first.received_at, True)
        assert await store.reserve(who, key, "a" * 64, uuid4(), peek=True) == again
        with pytest.raises(AppError) as error:
            await store.reserve(who, key, "b" * 64, uuid4(), peek=False)
        assert error.value.code == "IDEMPOTENCY_KEY_REUSED"
        # 다른 주체가 같은 키를 써도 기록이 섞이지 않는다.
        other = await store.reserve(identity("t"), key, "b" * 64, uuid4(), peek=False)
        assert other.replay is False and 0 < await client.pttl(store.receipt_key(who.subject, key)) <= 86400000
    with_redis(scenario)


def test_redis_daily_limits_per_opportunity_subject_and_ip():
    async def scenario(store, client):
        opportunity = uuid4()
        await store.reserve(identity("s", "i", opportunity), uuid4(), "a" * 64, uuid4(), peek=False)
        with pytest.raises(AppError) as error:
            await store.reserve(identity("s", "i", opportunity), uuid4(), "a" * 64, uuid4(), peek=False)
        assert error.value.code == "DAILY_QUOTA_EXCEEDED" and 1 <= error.value.retry_after <= 86400
        for _ in range(PER_SUBJECT - 1):
            await store.reserve(identity("s", "i"), uuid4(), "a" * 64, uuid4(), peek=False)
        with pytest.raises(AppError) as error:
            await store.reserve(identity("s", "j"), uuid4(), "a" * 64, uuid4(), peek=False)
        assert error.value.code == "DAILY_QUOTA_EXCEEDED"
        # 세션을 새로 만들어 주체를 바꿔도 같은 IP의 하루 한도는 남는다.
        for number in range(PER_IP - PER_SUBJECT):
            await store.reserve(identity(f"fresh-{number}", "i"), uuid4(), "a" * 64, uuid4(), peek=False)
        with pytest.raises(AppError) as error:
            await store.reserve(identity("another", "i"), uuid4(), "a" * 64, uuid4(), peek=False)
        assert error.value.code == "DAILY_QUOTA_EXCEEDED"
        assert (await store.reserve(identity("another", "k"), uuid4(), "a" * 64, uuid4(), peek=False)).replay is False
    with_redis(scenario)


def test_redis_kst_rollover_resets_counts_and_corrupt_state_fails_closed():
    async def scenario(store, client):
        seconds, _ = await client.time()
        today = (seconds + 32400) // 86400
        await client.hset(store.limits_key, mapping={"day": today - 1, "i:" + identity().ip: 999})
        assert (await store.reserve(identity(), uuid4(), "a" * 64, uuid4(), peek=False)).replay is False
        assert await client.hget(store.limits_key, "day") == str(today)
        for broken in ({"day": today + 1}, {"day": "x"}, {"day": today, "i:" + identity().ip: "x"}):
            await client.delete(store.limits_key)
            await client.hset(store.limits_key, mapping=broken)
            with pytest.raises(AppError) as error:
                await store.reserve(identity(), uuid4(), "a" * 64, uuid4(), peek=False)
            assert error.value.code == "SERVICE_UNAVAILABLE"
    with_redis(scenario)


def test_identity_rejects_raw_or_reused_values():
    for values in (("192.0.2.1", "a" * 64, "b" * 64), ("a" * 64, "a" * 64, "b" * 64)):
        with pytest.raises(ValueError):
            ReportIdentity(*values)


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


class Limits:
    async def check_http(self, identities, member):
        return None


class RecordingService:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    async def create(self, subject_id, ip, key, body):
        self.calls.append(("create", subject_id, ip, key, body))
        if self.error:
            raise self.error
        return SimpleNamespace(model_dump=lambda mode: {"report_id": str(UUID(int=1)), "received_at": "2026-10-17T00:00:00Z"})

    async def listing(self, status, page, page_size):
        self.calls.append(("listing", status, page, page_size))
        if self.error:
            raise self.error
        return SimpleNamespace(model_dump=lambda mode: {"items": [], "page": page, "page_size": page_size, "total": 0})

    async def update(self, report_id, body, *, actor_id, request_id):
        self.calls.append(("update", report_id, body, actor_id, request_id))
        if self.error:
            raise self.error
        return SimpleNamespace(model_dump=lambda mode: {"report_id": str(report_id)})


def client_for(service, members=None):
    app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
    app.state.session_service = SessionService(FakeStore())
    app.state.admission_service = AdmissionService(Limits(), identity_key=bytes(range(32)))
    app.state.report_service = service
    client = TestClient(app, base_url="https://testserver", client=("192.0.2.1", 50000), raise_server_exceptions=False)
    client.get("/api/v1/me")  # 익명 세션과 CSRF 쿠키를 받은 뒤 회원 판정 자리를 바꾼다
    if members is not None:
        app.state.member_service = members
    return client


REPORT = {"opportunity": {"id": str(UUID(int=7)), "version": 1}, "type": "broken_link", "note": None}
UPDATE = {"base_version": 1, "status": "in_progress", "resolution_note": None}


def test_anonymous_report_uses_session_subject_and_peer_without_trusting_body_or_headers():
    service = RecordingService()
    with client_for(service) as client:
        key = str(uuid4())
        response = client.post("/api/v1/reports", json=REPORT, headers={**csrf(client), "Idempotency-Key": key, "X-Forwarded-For": "203.0.113.9"})
        assert response.status_code == 201 and response.headers["cache-control"] == "no-store"
        assert set(response.json()) == {"report_id", "received_at"}
        (_, subject, ip, used_key, sent), = service.calls
        assert isinstance(subject, UUID) and ip == "192.0.2.1" and used_key == key and sent.type == "broken_link"


def test_report_without_csrf_key_or_with_injected_fields_never_reaches_service():
    service = RecordingService()
    with client_for(service) as client:
        headers = {**csrf(client), "Idempotency-Key": str(uuid4())}
        assert client.post("/api/v1/reports", json=REPORT, headers={"Idempotency-Key": str(uuid4())}).json()["code"] == "CSRF_FAILED"
        assert client.post("/api/v1/reports", json=REPORT, headers={**headers, "Origin": "https://attacker.example"}).json()["code"] == "CSRF_FAILED"
        assert client.post("/api/v1/reports", json=REPORT, headers=csrf(client)).status_code == 422
        assert client.post("/api/v1/reports?reporter=1", json=REPORT, headers=headers).status_code == 422
        injected = client.post("/api/v1/reports", json={**REPORT, "reporter_id": str(uuid4()), "status": "resolved"}, headers=headers)
        assert injected.status_code == 422 and {f["reason"] for f in injected.json()["fields"]} == {"unknown_field"}
        private = client.post("/api/v1/reports", json={**REPORT, "note": "제 번호 010-1234-5678로 연락 주세요"}, headers=headers)
        assert private.status_code == 422 and private.json()["fields"] == [{"path": "note", "reason": "invalid_value"}]
        assert "010-1234-5678" not in private.text
        other = client.post("/api/v1/reports", json={**REPORT, "type": "other"}, headers=headers)
        assert other.json()["fields"] == [{"path": "note", "reason": "required_with"}]
        assert service.calls == []


@pytest.mark.parametrize(("method", "path", "payload"), [
    ("get", "/api/v1/admin/reports", None),
    ("patch", f"/api/v1/admin/reports/{UUID(int=3)}", UPDATE),
])
@pytest.mark.parametrize("outcome", ["UNAUTHENTICATED", "FORBIDDEN", "MFA_REQUIRED"])
def test_non_operator_or_unverified_operator_never_reaches_report_admin(method, path, payload, outcome):
    members, service = Members(outcome), RecordingService()
    with client_for(service, members) as client:
        kwargs = {"json": payload, "headers": csrf(client)} if payload else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.json()["code"] == outcome and response.status_code in (401, 403)
        assert members.calls == [True] and service.calls == []


def test_operator_list_and_update_use_server_actor_and_request_id():
    service = RecordingService()
    with client_for(service, Members(SimpleNamespace(id=OPERATOR, role="admin"))) as client:
        listed = client.get("/api/v1/admin/reports?status=received&page=2&page_size=5")
        assert listed.status_code == 200 and listed.headers["cache-control"] == "no-store"
        report_id = uuid4()
        response = client.patch(f"/api/v1/admin/reports/{report_id}", json=UPDATE, headers=csrf(client))
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert service.calls[0] == ("listing", "received", 2, 5)
        (name, target, sent, actor, request_id) = service.calls[1]
        assert (name, target, sent.status, actor, request_id) == ("update", report_id, "in_progress", OPERATOR, response.headers["x-request-id"])


def test_admin_rejects_csrf_bad_filters_and_injected_fields_before_service():
    service = RecordingService()
    with client_for(service, Members(SimpleNamespace(id=OPERATOR, role="admin"))) as client:
        for query in ("status=open", "page=0", "page_size=21", "owner_id=1", "status=received&status=resolved"):
            assert client.get("/api/v1/admin/reports?" + query).status_code == 422
        url = f"/api/v1/admin/reports/{uuid4()}"
        assert client.patch(url, json=UPDATE).json()["code"] == "CSRF_FAILED"
        assert client.patch(url + "?actor_id=1", json=UPDATE, headers=csrf(client)).status_code == 422
        injected = client.patch(url, json={**UPDATE, "actor_id": str(uuid4()), "version": 9}, headers=csrf(client))
        assert {f["reason"] for f in injected.json()["fields"]} == {"unknown_field"}
        closing = client.patch(url, json={"base_version": 2, "status": "resolved", "resolution_note": None}, headers=csrf(client))
        assert closing.json()["fields"] == [{"path": "resolution_note", "reason": "required_with"}]
        assert client.patch("/api/v1/admin/reports/not-a-uuid", json=UPDATE, headers=csrf(client)).status_code == 422
        assert service.calls == []


@pytest.mark.parametrize("code", ["NOT_FOUND", "VERSION_CONFLICT", "INVALID_STATE_TRANSITION", "SERVICE_UNAVAILABLE"])
def test_report_errors_keep_common_error_contract(code):
    with client_for(RecordingService(AppError(code)), Members(SimpleNamespace(id=OPERATOR, role="admin"))) as client:
        response = client.patch(f"/api/v1/admin/reports/{uuid4()}", json=UPDATE, headers=csrf(client))
        assert response.json()["code"] == code and set(response.json()) == {"code", "message", "request_id"}


def test_daily_quota_returns_retry_after():
    with client_for(RecordingService(AppError("DAILY_QUOTA_EXCEEDED", retry_after=120))) as client:
        response = client.post("/api/v1/reports", json=REPORT, headers={**csrf(client), "Idempotency-Key": str(uuid4())})
        assert response.status_code == 429 and response.headers["retry-after"] == "120"


def test_end_to_end_report_then_operator_closes_with_audit_linked_to_request_id():
    with open_test_database("sqlite") as db:
        opportunity_id = seed(db)
        service = service_for(db)
        with client_for(service, Members(SimpleNamespace(id=OPERATOR, role="admin"))) as client:
            payload = {"opportunity": {"id": str(opportunity_id), "version": 1}, "type": "wrong_schedule_or_location", "note": "활동 장소가 바뀌었다고 기관에서 안내했어요"}
            created = client.post("/api/v1/reports", json=payload, headers={**csrf(client), "Idempotency-Key": str(uuid4())})
            assert created.status_code == 201
            report_id = created.json()["report_id"]
            listed = client.get("/api/v1/admin/reports?status=received").json()
            assert listed["total"] == 1 and listed["items"][0]["note"] == payload["note"] and listed["items"][0]["version"] == 1
            started = client.patch(f"/api/v1/admin/reports/{report_id}", json=UPDATE, headers=csrf(client))
            closed = client.patch(f"/api/v1/admin/reports/{report_id}", json={"base_version": 2, "status": "resolved", "resolution_note": "공고 장소 정정 요청함"}, headers=csrf(client))
            assert started.json()["status"] == "in_progress" and closed.json()["status"] == "resolved" and closed.json()["version"] == 3
            stale = client.patch(f"/api/v1/admin/reports/{report_id}", json={"base_version": 2, "status": "dismissed", "resolution_note": "중복"}, headers=csrf(client))
            assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
            assert set(db.scalars(select(AuditEvent.request_id))) == {started.headers["x-request-id"], closed.headers["x-request-id"]}


def test_unconfigured_report_storage_fails_closed():
    app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
    with pytest.raises(AppError) as error:
        asyncio.run(app.state.report_service.create(uuid4(), "192.0.2.1", str(uuid4()), body(uuid4())))
    assert error.value.code == "SERVICE_UNAVAILABLE"
    for call in (lambda: app.state.report_service.listing(None, 1, 20),
                 lambda: app.state.report_service.update(uuid4(), update_body(1, "in_progress"), actor_id=OPERATOR, request_id=REQUEST_ID),
                 lambda: app.state.report_service.purge(10)):
        with pytest.raises(AppError) as error:
            asyncio.run(call())
        assert error.value.code == "SERVICE_UNAVAILABLE"


# ---- 마이그레이션 ----

@BACKENDS
def test_upgrade_keeps_existing_reports_and_downgrade_drops_only_unrestorable_rows(backend):
    from alembic import command
    from sqlalchemy import Integer, String, Uuid, column, table
    from app.persistence.base import UTCDateTime
    from tests.test_migrations import migration_config

    with open_test_database(backend) as db:
        config = migration_config(db)
        command.upgrade(config, "0009_role_catalog_draft")
        opportunity_id = uuid4()
        source = uuid4()
        db.execute(insert(Source.__table__), {"id": source, "code": "fictional-old", "name": "가상 출처", "base_url": "https://example.org", "enabled": False})
        db.execute(insert(OpportunityDocument.__table__), {"id": opportunity_id, "source_id": source, "external_id": "old"})
        db.execute(insert(OpportunityVersion.__table__), opportunity_values(opportunity_id, 1))
        old = table("reports", column("id", Uuid), column("opportunity_id", Uuid), column("opportunity_version", Integer),
                    column("type", String), column("status", String), column("version", Integer), column("received_at", UTCDateTime()))
        report_id = uuid4()
        db.execute(insert(old), {"id": report_id, "opportunity_id": opportunity_id, "opportunity_version": 1,
                                 "type": "broken_link", "status": "received", "version": 1, "received_at": NOW})
        command.upgrade(config, "head")
        row = db.execute(select(Report.__table__)).mappings().one()
        assert (row["id"], row["status"], row["updated_at"], row["purged_at"]) == (report_id, "received", NOW, None)
        purged = uuid4()
        db.execute(insert(Report), {"id": purged, "opportunity_id": opportunity_id, "opportunity_version": 1, "type": "other",
                                    "status": "dismissed", "version": 3, "received_at": NOW, "updated_at": NOW, "purged_at": NOW})
        command.downgrade(config, "0009_role_catalog_draft")
        assert db.execute(select(old.c.id)).scalars().all() == [report_id]
