"""SQLAlchemy 공통 메타데이터와 시간대 검증. 연결은 여기서 만들지 않는다."""

from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from app.contracts.time import to_utc


class UTCDateTime(TypeDecorator[datetime]):
    """모든 쓰기에서 시간대 없는 시각을 거절하고 UTC로 정규화한다."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return to_utc(value) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        # SQLite 검증 DB는 시간대를 보관하지 않는다. PostgreSQL timestamptz는 보존한다.
        if dialect.name == "sqlite" and value.tzinfo is None:
            from datetime import UTC
            return value.replace(tzinfo=UTC)
        return to_utc(value)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })
