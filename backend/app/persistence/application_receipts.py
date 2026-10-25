"""지원서 저장 응답 기록. 승인 본문·키·원래 참조를 저장하지 않는다."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.base import Base, UTCDateTime


class ApplicationWriteReceipt(Base):
    __tablename__ = 'application_write_receipts'
    __table_args__ = (
        CheckConstraint('length(input_hash) = 64', name='input_hash'),
        CheckConstraint('intent_hash IS NULL OR length(intent_hash) = 64', name='intent_hash'),
        CheckConstraint('version > 0 AND profile_version > 0', name='versions'),
        CheckConstraint('expires_at > recorded_at', name='expiry'),
        UniqueConstraint('owner_id', 'intent_hash', name='uq_application_receipts_intent'),
        Index('ix_application_receipts_owner_expiry', 'owner_id', 'expires_at'),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    key_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    intent_hash: Mapped[str | None] = mapped_column(String(64))
    document_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    profile_id: Mapped[UUID] = mapped_column(Uuid)
    profile_version: Mapped[int] = mapped_column(Integer)
    saved_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())


@event.listens_for(ApplicationWriteReceipt, 'before_update')
def reject_receipt_update(mapper, connection, target):
    raise ValueError('저장 응답 기록을 덮어쓸 수 없습니다')
