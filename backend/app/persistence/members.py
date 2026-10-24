"""회원·동의·승인 저장본 모델 (W02-05, Plan/02).

본문은 암호문과 암호화 메타데이터만 받는다. 암호화 자체는 #25에서 구현한다.
서비스의 소유권·동의·확정/승인 검사를 DB 제약으로 대신하지 않는다.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, LargeBinary, String, UniqueConstraint, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.contracts.time import utc_now
from app.persistence.base import Base, UTCDateTime


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="role"),
        CheckConstraint("status IN ('active', 'suspended')", name="status"),
        CheckConstraint("length(kakao_subject) BETWEEN 1 AND 128", name="subject_length"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    kakao_subject: Mapped[str] = mapped_column(String(128), unique=True)
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user")
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (
        CheckConstraint("purpose IN ('ai_processing', 'storage')", name="purpose"),
        CheckConstraint("length(notice_version) BETWEEN 1 AND 32", name="notice_version"),
        CheckConstraint("withdrawn_at IS NULL OR withdrawn_at >= accepted_at", name="withdrawal_order"),
        Index("ix_consents_owner_purpose", "owner_id", "purpose", "accepted_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(32))
    notice_version: Mapped[str] = mapped_column(String(32))
    accepted_at: Mapped[datetime] = mapped_column(UTCDateTime())
    withdrawn_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ProfileDocument(Base):
    """논리 ProfileVersion의 안정 ID·소유자. 회원당 프로필 계열은 하나다."""

    __tablename__ = "profile_documents"
    __table_args__ = (UniqueConstraint("owner_id", "id", name="uq_profile_documents_owner_identity"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)


class EncryptedContent:
    """키 원문은 보관하지 않는다. AES-GCM의 태그는 ciphertext 뒤에 포함한다."""

    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[str] = mapped_column(String(128))
    algorithm: Mapped[str] = mapped_column(String(16))
    schema_version: Mapped[int] = mapped_column(Integer)


def encrypted_constraints():
    return (
        UniqueConstraint("key_id", "nonce"),
        CheckConstraint("length(ciphertext) BETWEEN 17 AND 262144", name="ciphertext_length"),
        CheckConstraint("length(nonce) = 12", name="nonce_length"),
        CheckConstraint("length(key_id) BETWEEN 1 AND 128", name="key_reference"),
        CheckConstraint("algorithm = 'AES-256-GCM'", name="algorithm"),
        CheckConstraint("schema_version > 0", name="schema_version"),
    )


class ProfileVersion(EncryptedContent, Base):
    __tablename__ = "profile_versions"
    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "profile_id"], ["profile_documents.owner_id", "profile_documents.id"], ondelete="CASCADE"),
        UniqueConstraint("owner_id", "profile_id", "version"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("saved_at >= confirmed_at", name="confirmation_order"),
        *encrypted_constraints(),
    )

    profile_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    confirmed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    saved_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class ApplicationDocument(Base):
    """논리 ApplicationDraft의 안정 ID. 프로필 계열 삭제 시 문서 전체를 삭제한다."""

    __tablename__ = "application_documents"
    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "profile_id"], ["profile_documents.owner_id", "profile_documents.id"], ondelete="CASCADE"),
        UniqueConstraint("owner_id", "id", "profile_id"),
        Index("ix_application_documents_profile", "owner_id", "profile_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    profile_id: Mapped[UUID] = mapped_column(Uuid)


class ApplicationDraft(EncryptedContent, Base):
    """사용자 승인 후 회원이 저장한 버전만 표현한다. 편집 초안은 Redis 대상이다."""

    __tablename__ = "application_drafts"
    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "document_id", "profile_id"], ["application_documents.owner_id", "application_documents.id", "application_documents.profile_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["owner_id", "profile_id", "profile_version"], ["profile_versions.owner_id", "profile_versions.profile_id", "profile_versions.version"], ondelete="CASCADE"),
        CheckConstraint("version > 0 AND profile_version > 0 AND opportunity_version > 0", name="versions"),
        CheckConstraint("saved_at >= approved_at", name="approval_order"),
        Index("ix_application_drafts_profile", "owner_id", "profile_id", "profile_version"),
        *encrypted_constraints(),
    )

    document_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    profile_id: Mapped[UUID] = mapped_column(Uuid)
    profile_version: Mapped[int] = mapped_column(Integer)
    # #17에서 공고 저장 모델과 복합 FK를 연결한다.
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    approved_at: Mapped[datetime] = mapped_column(UTCDateTime())
    saved_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


@event.listens_for(ProfileVersion, "before_update")
@event.listens_for(ApplicationDraft, "before_update")
def reject_saved_version_update(mapper, connection, target) -> None:
    """ORM 편집으로 승인 저장본을 덮어쓰지 않는다. 새 승인 버전을 INSERT한다.

    bulk SQL의 차단은 #18 PostgreSQL 마이그레이션 트리거에서 연결한다.
    """
    raise ValueError("승인 저장본은 새 버전으로 저장해야 합니다")
