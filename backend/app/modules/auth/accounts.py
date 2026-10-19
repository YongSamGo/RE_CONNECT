"""검증한 카카오 신원과 내부 계정 연결. 브라우저가 역할/계정 상태를 선택하지 않는다."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.business_errors import AppError
from app.modules.auth.service import Identity
from app.persistence.members import User


@dataclass(frozen=True)
class Account:
    id: UUID
    role: str


class SqlAccountRepository:
    def __init__(self, transaction):
        self.transaction = transaction

    @staticmethod
    def _account(row):
        if row is None or row["status"] != "active":
            return None
        if row["role"] not in {"user", "admin"}:
            raise AppError("SERVICE_UNAVAILABLE")
        return Account(row["id"], row["role"])

    def link(self, identity: Identity) -> Account:
        # 타입 표시에 의존하지 않고 검증된 숫자 신원만 다시 검사한다.
        identity = Identity(identity.subject)
        try:
            with self.transaction() as db:
                dialect = db.get_bind().dialect.name
                if dialect == "postgresql":
                    db.execute(text("SET LOCAL statement_timeout = 5000"))
                    db.execute(text("SET LOCAL lock_timeout = 1000"))
                insert = {"postgresql": pg_insert, "sqlite": sqlite_insert}.get(dialect)
                if insert is None:
                    raise AppError("SERVICE_UNAVAILABLE")
                # 고유 제약으로 동시 첫 로그인을 한 User에 연결한다.
                statement = insert(User).values(id=uuid4(), kakao_subject=identity.subject, role="user", status="active")
                db.execute(statement.on_conflict_do_nothing(index_elements=[User.kakao_subject]))
                row = db.execute(select(User.__table__).where(User.kakao_subject == identity.subject).with_for_update()).mappings().one_or_none()
                account = self._account(row)
                if account is None:
                    raise AppError("FORBIDDEN")
                return account
        except SQLAlchemyError:
            raise AppError("SERVICE_UNAVAILABLE") from None

    def get(self, account_id: UUID) -> Account | None:
        try:
            with self.transaction() as db:
                row = db.execute(select(User.__table__).where(User.id == account_id)).mappings().one_or_none()
                return self._account(row)
        except SQLAlchemyError:
            raise AppError("SERVICE_UNAVAILABLE") from None
