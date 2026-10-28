"""감사 기록 읽기·만료 정리. 보관기간이 지난 기록은 정리 전이라도 조회에서 뺀다."""

from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.business_errors import AppError
from app.modules.audit.models import AuditEventView, AuditList, AuditSearch
from app.persistence.operations import AuditEvent as A

_COLUMNS = (A.id, A.at, A.actor_id, A.actor_role, A.action, A.target_type, A.target_id, A.result, A.request_id)


class SqlAuditRepository:
    def __init__(self, connect, transaction):
        self.connect, self.transaction = connect, transaction

    def page(self, search: AuditSearch, now: datetime) -> AuditList:
        window = (A.at >= search.start, A.at < search.end, A.expires_at > now)
        offset = (search.page - 1) * search.page_size
        try:
            with self.connect() as db:
                total = db.scalar(select(func.count()).select_from(A).where(*window))
                rows = [] if offset >= total else db.execute(
                    select(*_COLUMNS).where(*window).order_by(A.at.desc(), A.id.desc())
                    .offset(offset).limit(search.page_size)).mappings().all()
            # 저장값이 계약 밖이면 그대로 내보내지 않고 실패로 닫는다.
            items = [AuditEventView(event_id=row["id"], **{key: row[key] for key in row if key != "id"}) for row in rows]
            return AuditList(items=items, page=search.page, page_size=search.page_size, total=total)
        except (SQLAlchemyError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    def prune(self, now: datetime) -> int:
        try:
            with self.transaction() as db:
                return db.execute(delete(A).where(A.expires_at <= now)).rowcount
        except SQLAlchemyError:
            raise AppError("SERVICE_UNAVAILABLE") from None


class UnavailableAuditRepository:
    def page(self, *args):
        raise AppError("SERVICE_UNAVAILABLE")

    prune = page
