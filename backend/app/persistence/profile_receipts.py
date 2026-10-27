"""저장 응답 재전송용 최소 메타데이터. 본문과 원래 자원 참조는 저장하지 않는다."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.base import Base, UTCDateTime


class ProfileWriteReceipt(Base):
    __tablename__ = 'profile_write_receipts'
    __table_args__ = (
        CheckConstraint('length(input_hash) = 64', name='input_hash'),
        CheckConstraint('intent_hash IS NULL OR length(intent_hash) = 64', name='intent_hash'),
        UniqueConstraint('owner_id', 'intent_hash', name='uq_profile_receipts_intent'),
        CheckConstraint('version > 0 AND (replaced_version IS NULL OR replaced_version > 0)', name='versions'),
        CheckConstraint('expires_at > recorded_at', name='expiry'),
        Index('ix_profile_receipts_owner_expiry', 'owner_id', 'expires_at'),
    )

    owner_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    key_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    intent_hash: Mapped[str | None] = mapped_column(String(64))
    # 프로필 삭제 후에도 재전송 기록을 남겨 같은 키로 되살리는 것을 막는다.
    profile_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    saved_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created: Mapped[bool] = mapped_column(Boolean)
    replaced_version: Mapped[int | None] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())


@event.listens_for(ProfileWriteReceipt, 'before_update')
def reject_receipt_update(mapper, connection, target):
    raise ValueError('저장 응답 기록을 덮어쓸 수 없습니다')
