"""출처 중복·승인 공개 포인터·감사/삭제 생존 경계를 DB 제약으로 검증한다."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import DataError, IntegrityError

from app.persistence import AuditEvent, DeletionRecord, IngestionRun, OpportunityDocument, OpportunityPublication, OpportunityVersion, Report, Source, User
from tests.persistence_helpers import NOW, OPPORTUNITY_ID, opportunity_values, seed_opportunity
from tests.test_member_models import db, saved_draft, seed
from app.persistence import ApplicationDraft


def test_same_source_external_id_is_unique_but_manual_null_ids_are_not_merged(db):
    source_id, _ = seed_opportunity(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(OpportunityDocument), {"source_id": source_id, "external_id": "fictional-external"})
    db.execute(insert(OpportunityDocument), [{"source_id": source_id, "external_id": None}, {"source_id": source_id, "external_id": None}])
    assert len(db.execute(select(OpportunityDocument.id)).all()) == 3


def test_pending_or_cross_opportunity_version_cannot_be_published(db):
    source_id, opportunity_id = seed_opportunity(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(OpportunityPublication), {"opportunity_id": opportunity_id, "version": 1})
    db.execute(insert(OpportunityVersion), opportunity_values(version=2, review_status="approved", reviewed_at=NOW))
    other = uuid4()
    db.execute(insert(OpportunityDocument), {"id": other, "source_id": source_id, "external_id": "fictional-other"})
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(OpportunityPublication), {"opportunity_id": other, "version": 2})
    db.execute(insert(OpportunityPublication), {"opportunity_id": opportunity_id, "version": 2})


def test_one_public_pointer_keeps_old_approved_version_during_pending_change(db):
    _, opportunity_id = seed_opportunity(db)
    db.execute(update(OpportunityVersion).where(OpportunityVersion.opportunity_id == opportunity_id).values(review_status="approved", reviewed_at=NOW))
    db.execute(insert(OpportunityPublication), {"opportunity_id": opportunity_id, "version": 1})
    db.execute(insert(OpportunityVersion), opportunity_values(version=2, title="변경 검수 대기"))
    assert db.execute(select(OpportunityPublication.version)).scalar_one() == 1
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(update(OpportunityPublication).values(version=2))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(OpportunityPublication), {"opportunity_id": opportunity_id, "version": 1})


def test_published_version_must_be_unpublished_before_hide(db):
    _, opportunity_id = seed_opportunity(db)
    db.execute(update(OpportunityVersion).values(review_status="approved", reviewed_at=NOW))
    db.execute(insert(OpportunityPublication), {"opportunity_id": opportunity_id, "version": 1})
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(update(OpportunityVersion).values(review_status="hidden"))
    db.execute(delete(OpportunityPublication))
    db.execute(update(OpportunityVersion).values(review_status="hidden"))


@pytest.mark.parametrize("updates", [
    {"version": 0}, {"review_status": "approved"}, {"review_status": "arbitrary"},
    {"description_text": "x" * 5001}, {"content_hash": "short"},
    {"hours_per_week": -1}, {"activity_province": None, "activity_district": "yongsan"},
])
def test_invalid_public_version_metadata_is_rejected(db, updates):
    source_id = uuid4()
    db.execute(insert(Source), {"id": source_id, "code": "fictional", "name": "가상", "base_url": "https://example.org"})
    db.execute(insert(OpportunityDocument), {"id": OPPORTUNITY_ID, "source_id": source_id, "external_id": "test"})
    # PostgreSQL은 varchar 한도에서 먼저 DataError, SQLite는 CHECK에서 IntegrityError를 낸다.
    with pytest.raises((IntegrityError, DataError)), db.begin_nested():
        db.execute(insert(OpportunityVersion), opportunity_values(**updates))


def test_application_cannot_reference_nonexistent_opportunity_version(db):
    owner, _, profile_id, document_id = seed(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(ApplicationDraft), saved_draft(owner, profile_id, document_id, opportunity_version=2))


def test_report_requires_existing_version_and_complete_optional_encryption_envelope(db):
    seed_opportunity(db)
    values = {"opportunity_id": OPPORTUNITY_ID, "opportunity_version": 1, "type": "broken_link"}
    db.execute(insert(Report), values)
    for updates in ({"opportunity_version": 99}, {"details_ciphertext": b"x" * 20}, {"type": "other"}, {"status": "unknown"}):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(insert(Report), values | updates)


@pytest.mark.parametrize("updates", [
    {"status": "succeeded", "finished_at": None},
    {"status": "running", "finished_at": NOW},
    {"status": "failed", "finished_at": NOW - timedelta(seconds=1)},
    {"status": "failed", "finished_at": NOW, "failure_code": "private-token"},
    {"fetched_count": -1},
])
def test_ingestion_counters_and_completion_are_consistent(db, updates):
    source_id, _ = seed_opportunity(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(IngestionRun), {"source_id": source_id, "status": "running", "started_at": NOW, **updates})


def test_user_deletion_preserves_minimal_audit_and_restore_deletion_record(db):
    owner = uuid4()
    db.execute(insert(User), {"id": owner, "kakao_subject": "fictional-deleted"})
    db.execute(insert(AuditEvent), {"actor_id": owner, "actor_role": "user", "action": "access.denied", "target_type": "user", "target_id": owner, "result": "denied", "request_id": "req_" + "a" * 32, "at": NOW, "expires_at": NOW + timedelta(days=30)})
    db.execute(insert(DeletionRecord), {"owner_id": owner, "scope": "account", "target_id": owner, "status": "completed", "deleted_at": NOW, "expires_at": NOW + timedelta(days=30)})
    db.execute(delete(User).where(User.id == owner))
    assert db.execute(select(AuditEvent.actor_id)).scalar_one() == owner
    assert db.execute(select(DeletionRecord.owner_id)).scalar_one() == owner


def test_audit_rejects_arbitrary_messages_and_unpaired_target(db):
    values = {"actor_role": "system", "action": "access.denied", "target_type": None, "target_id": None, "result": "denied", "request_id": "req_" + "a" * 32, "at": NOW, "expires_at": NOW + timedelta(days=30)}
    for updates in ({"action": "private-body"}, {"target_id": uuid4()}, {"expires_at": NOW}):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(insert(AuditEvent), values | updates)


def test_permanent_metadata_does_not_create_journey_or_secret_columns():
    from app.persistence import Base

    assert len(Base.metadata.tables) == 16  # 기존15개 + 본문 없는 프로필 저장 응답 기록
    assert not any("journey" in name for name in Base.metadata.tables)
    for table in Base.metadata.tables.values():
        assert not {"transcript", "conversation", "otp", "access_token", "service_key", "key_material"} & set(table.columns.keys())
