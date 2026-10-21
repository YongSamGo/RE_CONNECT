"""공고·수집·운영의 영구 저장 경계 (W02-06, Plan/02 §1·§3·§6).

출처 설정에 인증키를, 감사/삭제 기록에 원문을 저장하지 않는다. 공개 포인터는
같은 공고의 approved 버전만 참조할 수 있다. Journey는 영구 테이블/FK가 아니다.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, LargeBinary, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.contracts.time import utc_now
from app.persistence.base import Base, UTCDateTime

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("length(code) BETWEEN 1 AND 64", name="code"),
        CheckConstraint("length(name) BETWEEN 1 AND 200", name="name"),
        CheckConstraint("base_url LIKE 'https://%'", name="https"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(2000))
    terms_url: Mapped[str | None] = mapped_column(String(2000))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="status"),
        CheckConstraint("fetched_count >= 0 AND created_count >= 0 AND changed_count >= 0 AND rejected_count >= 0", name="counts"),
        CheckConstraint("(status = 'running' AND finished_at IS NULL) OR (status <> 'running' AND finished_at IS NOT NULL AND finished_at >= started_at)", name="completion"),
        CheckConstraint("failure_code IS NULL OR failure_code IN ('network', 'parse', 'response_limit', 'source_unavailable', 'cancelled', 'invalid_payload')", name="failure_code"),
        Index("ix_ingestion_runs_source_started", "source_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    failure_code: Mapped[str | None] = mapped_column(String(32))
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)


class RoleDefinition(Base):
    __tablename__ = "role_definitions"
    __table_args__ = (
        CheckConstraint("length(id) BETWEEN 2 AND 64", name="id_length"),
        CheckConstraint("length(name) BETWEEN 1 AND 100", name="name"),
        CheckConstraint("length(description) BETWEEN 1 AND 1000", name="description"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(1000))
    skill_tags: Mapped[list] = mapped_column(JSON_VALUE)
    aliases: Mapped[list] = mapped_column(JSON_VALUE)
    experience_rules: Mapped[list] = mapped_column(JSON_VALUE)


class OpportunityDocument(Base):
    """출처 식별과 안정 공고 ID. null external_id의 수동 중복 대조는 #47에서 수행한다."""

    __tablename__ = "opportunity_documents"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        CheckConstraint("external_id IS NULL OR length(external_id) BETWEEN 1 AND 200", name="external_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"))
    external_id: Mapped[str | None] = mapped_column(String(200))


class OpportunityVersion(Base):
    __tablename__ = "opportunity_versions"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "version", "review_status"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("activity_type IN ('employment', 'volunteering')", name="activity_type"),
        CheckConstraint("recruitment_status IN ('open', 'closed', 'unknown')", name="recruitment_status"),
        CheckConstraint("review_status IN ('pending', 'approved', 'rejected', 'hidden')", name="review_status"),
        CheckConstraint("review_status <> 'approved' OR reviewed_at IS NOT NULL", name="approved_review_time"),
        CheckConstraint("activity_province IS NULL OR activity_province IN ('seoul', 'gyeonggi', 'incheon')", name="province"),
        CheckConstraint("activity_district IS NULL OR activity_province IS NOT NULL", name="district_province"),
        CheckConstraint("hours_per_week IS NULL OR (hours_per_week >= 0 AND hours_per_week <= 168)", name="hours"),
        CheckConstraint("length(title) BETWEEN 1 AND 200 AND length(organization_name) BETWEEN 1 AND 200", name="title_organization"),
        CheckConstraint("description_text IS NULL OR length(description_text) BETWEEN 1 AND 5000", name="description_length"),
        CheckConstraint("length(content_hash) = 64", name="content_hash"),
        CheckConstraint("application_method IN ('online', 'phone', 'visit', 'email', 'mixed')", name="application_method"),
        Index("ix_opportunity_versions_public_search", "review_status", "recruitment_status", "activity_type", "activity_province"),
        Index("ix_opportunity_versions_freshness", "source_checked_at"),
    )

    opportunity_id: Mapped[UUID] = mapped_column(ForeignKey("opportunity_documents.id", ondelete="RESTRICT"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    organization_name: Mapped[str] = mapped_column(String(200))
    activity_type: Mapped[str] = mapped_column(String(16))
    is_public_job: Mapped[bool | None] = mapped_column(Boolean)
    role_tags: Mapped[list] = mapped_column(JSON_VALUE)
    skill_tags: Mapped[list] = mapped_column(JSON_VALUE)
    activity_province: Mapped[str | None] = mapped_column(String(16))
    activity_district: Mapped[str | None] = mapped_column(String(64))
    location_text: Mapped[str | None] = mapped_column(String(500))
    remote_allowed: Mapped[bool | None] = mapped_column(Boolean)
    schedule_text: Mapped[str | None] = mapped_column(String(500))
    hours_per_week: Mapped[float | None] = mapped_column(Float)
    paid: Mapped[bool | None] = mapped_column(Boolean)
    compensation_text: Mapped[str | None] = mapped_column(String(500))
    description_text: Mapped[str | None] = mapped_column(String(5000))
    description_truncated: Mapped[bool] = mapped_column(Boolean)
    requirements: Mapped[list] = mapped_column(JSON_VALUE)
    required_documents: Mapped[list | None] = mapped_column(JSON_VALUE, nullable=True)
    application_method: Mapped[str] = mapped_column(String(16))
    application_instructions: Mapped[str] = mapped_column(String(2000))
    source_url: Mapped[str] = mapped_column(String(2000))
    application_url: Mapped[str] = mapped_column(String(2000))
    deadline_date: Mapped[date | None] = mapped_column(Date)
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    recruitment_status: Mapped[str] = mapped_column(String(16))
    review_status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    source_checked_at: Mapped[datetime] = mapped_column(UTCDateTime())
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    content_hash: Mapped[str] = mapped_column(String(64))


class OpportunityPublication(Base):
    """공고당 하나의 공개 포인터. 같은 공고의 승인된 버전만 가리킨다."""

    __tablename__ = "opportunity_publications"
    __table_args__ = (
        ForeignKeyConstraint(["opportunity_id", "version", "review_status"], ["opportunity_versions.opportunity_id", "opportunity_versions.version", "opportunity_versions.review_status"], ondelete="RESTRICT"),
        CheckConstraint("review_status = 'approved'", name="approved_only"),
    )

    opportunity_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    review_status: Mapped[str] = mapped_column(String(16), default="approved", server_default="approved")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        ForeignKeyConstraint(["opportunity_id", "opportunity_version"], ["opportunity_versions.opportunity_id", "opportunity_versions.version"], ondelete="RESTRICT"),
        CheckConstraint("type IN ('already_closed', 'wrong_requirements', 'wrong_schedule_or_location', 'wrong_application_method', 'broken_link', 'other')", name="type"),
        CheckConstraint("status IN ('received', 'in_progress', 'resolved', 'dismissed')", name="status"),
        CheckConstraint("type <> 'other' OR details_ciphertext IS NOT NULL", name="other_details"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("(details_ciphertext IS NULL AND details_nonce IS NULL AND details_key_id IS NULL) OR (details_ciphertext IS NOT NULL AND details_nonce IS NOT NULL AND details_key_id IS NOT NULL AND length(details_ciphertext) BETWEEN 17 AND 16384 AND length(details_nonce) = 12 AND length(details_key_id) BETWEEN 1 AND 128)", name="details_envelope"),
        Index("ix_reports_status_received", "status", "received_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="received")
    version: Mapped[int] = mapped_column(Integer, default=1)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    # 임의 신고/처리 설명에 개인정보가 섞일 수 있어 평문 칸을 만들지 않는다.
    details_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    details_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    details_key_id: Mapped[str | None] = mapped_column(String(128))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("actor_role IN ('operator', 'user', 'system')", name="actor_role"),
        CheckConstraint("action IN ('opportunity.create', 'opportunity.update', 'opportunity.approve', 'opportunity.reject', 'opportunity.hide', 'opportunity.close', 'report.update', 'mfa.verify', 'mfa.fail', 'mfa.lock', 'role.grant', 'role.revoke', 'access.denied')", name="action"),
        CheckConstraint("target_type IS NULL OR target_type IN ('opportunity', 'report', 'user')", name="target_type"),
        CheckConstraint("(target_type IS NULL AND target_id IS NULL) OR (target_type IS NOT NULL AND target_id IS NOT NULL)", name="target_pair"),
        CheckConstraint("result IN ('success', 'denied', 'failed')", name="result"),
        CheckConstraint("length(request_id) BETWEEN 14 AND 36", name="request_id"),
        CheckConstraint("expires_at > at", name="expiry"),
        Index("ix_audit_events_at", "at"),
        Index("ix_audit_events_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    # 삭제 뒤 최소 식별값으로 남아야 하므로 생존 User FK로 묶지 않는다.
    actor_id: Mapped[UUID | None] = mapped_column(Uuid)
    actor_role: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(40))
    target_type: Mapped[str | None] = mapped_column(String(16))
    target_id: Mapped[UUID | None] = mapped_column(Uuid)
    result: Mapped[str] = mapped_column(String(16))
    request_id: Mapped[str] = mapped_column(String(36))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())


class DeletionRecord(Base):
    __tablename__ = "deletion_records"
    __table_args__ = (
        CheckConstraint("scope IN ('account', 'profile', 'application')", name="scope"),
        CheckConstraint("status IN ('pending', 'completed', 'failed')", name="status"),
        CheckConstraint("expires_at > deleted_at", name="expiry"),
        CheckConstraint("action IN ('legacy', 'profile_delete', 'application_delete', 'storage_withdraw', 'ai_withdraw', 'account_delete')", name='action'),
        CheckConstraint('generation >= 0 AND generation < 2147483647', name='generation'),
        Index("ix_deletion_records_expiry", "expires_at"),
        Index("ix_deletion_records_target", "scope", "target_id"),
        Index('ix_deletion_records_owner_status', 'owner_id', 'status'),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # 회원과 함께 삭제되면 복원 후 삭제 재적용이 불가능하다. 본문·외부 ID는 보관하지 않는다.
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    scope: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(24), default='legacy', server_default='legacy')
    generation: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    deleted_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
