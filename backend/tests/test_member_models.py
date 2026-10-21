"""회원 영구 모델의 실제 관계·제약·연쇄 삭제를 SQLite에서 검증한다.

PostgreSQL 스키마도 컴파일하지만 실제 PostgreSQL 실행 검증은 #18에서 연결한다.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from app.persistence import ApplicationDocument, ApplicationDraft, Base, Consent, ProfileDocument, ProfileVersion, User
from tests.persistence_helpers import OPPORTUNITY_ID, open_test_database, seed_opportunity

NOW = datetime(2026, 10, 17, tzinfo=UTC)


@pytest.fixture(params=["sqlite", "postgresql"])
def db(request):
    with open_test_database(request.param) as connection:
        Base.metadata.create_all(connection)
        yield connection


def encrypted(**updates):
    # 형식 시험용 가상 bytes. 암호화의 안전성 검증/실제 암호문은 #25에서 다룬다.
    return {"ciphertext": b"x" * 32, "nonce": b"n" * 12, "key_id": "test-key-reference", "algorithm": "AES-256-GCM", "schema_version": 1, **updates}


def seed(db, *, users=User):
    seed_opportunity(db)
    owner, other, profile_id, document_id = uuid4(), uuid4(), uuid4(), uuid4()
    db.execute(insert(users), [{"id": owner, "kakao_subject": "fictional-owner", 'role': 'user', 'status': 'active', 'created_at': NOW},
        {"id": other, "kakao_subject": "fictional-other", 'role': 'user', 'status': 'active', 'created_at': NOW}])
    db.execute(insert(ProfileDocument), {"id": profile_id, "owner_id": owner})
    db.execute(insert(ProfileVersion), {"owner_id": owner, "profile_id": profile_id, "version": 1, "confirmed_at": NOW, "saved_at": NOW, **encrypted()})
    db.execute(insert(ApplicationDocument), {"id": document_id, "owner_id": owner, "profile_id": profile_id})
    return owner, other, profile_id, document_id


def saved_draft(owner, profile_id, document_id, **updates):
    return {"owner_id": owner, "profile_id": profile_id, "profile_version": 1, "document_id": document_id, "version": 1, "opportunity_id": OPPORTUNITY_ID, "opportunity_version": 1, "approved_at": NOW, "saved_at": NOW, **encrypted(), **updates}


def test_saved_draft_must_reference_same_owner_document_and_profile_version(db):
    owner, other, profile_id, document_id = seed(db)
    db.execute(insert(ApplicationDraft), saved_draft(owner, profile_id, document_id))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(ApplicationDraft), saved_draft(other, profile_id, document_id, version=2, nonce=b"o" * 12))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(ApplicationDraft), saved_draft(owner, profile_id, document_id, version=2, profile_version=99, nonce=b"o" * 12))


def test_one_profile_identity_cannot_acquire_another_owner_in_later_version(db):
    owner, other, profile_id, _ = seed(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(ProfileVersion), {"owner_id": other, "profile_id": profile_id, "version": 2, "confirmed_at": NOW, "saved_at": NOW, **encrypted(nonce=b"o" * 12)})


def test_duplicate_or_nonpositive_profile_version_is_rejected(db):
    owner, _, profile_id, _ = seed(db)
    for version in (0, 1):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(insert(ProfileVersion), {"owner_id": owner, "profile_id": profile_id, "version": version, "confirmed_at": NOW, "saved_at": NOW, **encrypted(nonce=b"o" * 12)})


@pytest.mark.parametrize("updates", [
    {"ciphertext": b""}, {"nonce": b"bad"}, {"key_id": ""},
    {"algorithm": "plaintext"}, {"schema_version": 0},
    {"saved_at": NOW - timedelta(seconds=1)},
])
def test_incomplete_envelope_and_unapproved_time_are_rejected(db, updates):
    owner, _, profile_id, document_id = seed(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(ApplicationDraft), saved_draft(owner, profile_id, document_id, **updates))


def test_nonce_reuse_for_same_key_is_rejected_within_saved_entity(db):
    owner, _, profile_id, _ = seed(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(ProfileVersion), {"owner_id": owner, "profile_id": profile_id, "version": 2, "confirmed_at": NOW, "saved_at": NOW, **encrypted()})


def test_profile_family_delete_removes_all_versions_and_derived_documents(db):
    owner, _, profile_id, document_id = seed(db)
    db.execute(insert(ProfileVersion), {"owner_id": owner, "profile_id": profile_id, "version": 2, "confirmed_at": NOW, "saved_at": NOW, **encrypted(nonce=b"o" * 12)})
    db.execute(insert(ApplicationDraft), saved_draft(owner, profile_id, document_id))
    db.execute(delete(ProfileDocument).where(ProfileDocument.owner_id == owner))
    for model in (ProfileVersion, ApplicationDocument, ApplicationDraft):
        assert db.execute(select(model.__table__)).all() == []
    assert db.execute(select(User.id).where(User.id == owner)).scalar_one() == owner


def test_user_delete_cascades_consent_and_saved_material(db):
    owner, _, profile_id, document_id = seed(db)
    db.execute(insert(Consent), {"owner_id": owner, "purpose": "storage", "notice_version": "storage-2026-10-15", "accepted_at": NOW})
    db.execute(insert(ApplicationDraft), saved_draft(owner, profile_id, document_id))
    db.execute(delete(User).where(User.id == owner))
    for model in (Consent, ProfileDocument, ProfileVersion, ApplicationDocument, ApplicationDraft):
        assert db.execute(select(model.__table__)).all() == []


def test_consent_requires_known_purpose_and_ordered_withdrawal(db):
    owner, *_ = seed(db)
    for updates in ({"purpose": "all"}, {"withdrawn_at": NOW - timedelta(seconds=1)}, {"notice_version": ""}):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(insert(Consent), {"owner_id": owner, "purpose": "ai_processing", "notice_version": "ai-2026-10-15", "accepted_at": NOW, **updates})


def test_query_values_are_bound_parameters_and_do_not_change_ownership(db):
    owner, *_ = seed(db)
    malicious = "' OR 1=1 --"
    assert db.execute(select(User.id).where(User.kakao_subject == malicious)).all() == []
    assert db.execute(select(User.id).where(User.id == owner)).scalar_one() == owner


def test_timezone_is_required_and_values_roundtrip_as_utc(db):
    with pytest.raises(StatementError), db.begin_nested():
        db.execute(insert(User), {"kakao_subject": "fictional-naive", "created_at": NOW.replace(tzinfo=None)})
    db.execute(insert(User), {"kakao_subject": "fictional-aware", "created_at": NOW})
    assert db.execute(select(User.created_at).where(User.kakao_subject == "fictional-aware")).scalar_one() == NOW


def test_orm_cannot_overwrite_saved_version(db):
    owner, _, profile_id, _ = seed(db)
    with Session(bind=db, join_transaction_mode="create_savepoint") as session:
        saved = session.get(ProfileVersion, (profile_id, 1))
        saved.ciphertext = b"changed" * 10
        with pytest.raises(ValueError, match="새 버전"):
            session.flush()


def test_postgresql_schema_has_binary_envelopes_and_no_ephemeral_plaintext():
    ddl = "\n".join(str(CreateTable(table).compile(dialect=postgresql.dialect())) for table in Base.metadata.sorted_tables)
    assert "BYTEA" in ddl
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    for forbidden in ("transcript", "self_introduction", "motivation", "conversation", "journey_id", "access_token", "key_material"):
        assert forbidden not in ddl.lower()
