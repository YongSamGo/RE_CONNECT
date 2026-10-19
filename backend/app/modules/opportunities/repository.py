"""SQL 바인딩·명시적 공개 포인터·응답 허용 목록. 원문을 SQL 구문으로 조립하지 않는다."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import Date, case, cast, exists, func, or_, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.contracts.opportunity import OpportunityContent
from app.contracts.time import kst_date
from app.core.business_errors import AppError
from app.modules.opportunities.lifecycle import assess_lifecycle
from app.modules.opportunities.versions import IMPORTANT_FIELDS, IMPORTANT_STATUS_TRANSITIONS
from app.modules.opportunities.service import OpportunityPage, OpportunitySearch, OpportunitySummary, PublicOpportunity
from app.persistence.operations import OpportunityPublication as P, OpportunityVersion as V, RoleDefinition


class SqlPublicOpportunityRepository:
    def __init__(self, connect: Callable[[], AbstractContextManager[Connection]]):
        self.connect = connect

    @staticmethod
    def _base():
        pending = V.__table__.alias("pending")
        columns = set(IMPORTANT_FIELDS) - {"activity_region"}
        columns |= {"activity_province", "activity_district"}
        significant = [pending.c[name].is_distinct_from(V.__table__.c[name]) for name in sorted(columns)]
        significant += [(V.recruitment_status == before) & (pending.c.recruitment_status == after) for before, after in sorted(IMPORTANT_STATUS_TRANSITIONS)]
        change_pending = exists(select(1).select_from(pending).where(pending.c.opportunity_id == V.opportunity_id, pending.c.version > V.version, pending.c.review_status == "pending", or_(*significant)))
        return select(V.__table__, change_pending.label("change_pending")).join(P, (P.opportunity_id == V.opportunity_id) & (P.version == V.version)).where(P.review_status == "approved", V.review_status == "approved")

    @staticmethod
    def _tag_matches(column, pattern, dialect):
        values = (func.jsonb_array_elements_text(column).table_valued("value") if dialect == "postgresql" else func.json_each(column).table_valued("key", "value"))
        return exists(select(1).select_from(values).where(values.c.value.ilike(pattern, escape="\\")))

    def _search(self, statement, search, now, dialect):
        statement = statement.where(V.recruitment_status.in_(("open", "unknown")), or_(V.deadline_at.is_(None), V.deadline_at > now), or_(V.deadline_at.is_not(None), V.deadline_date.is_(None), V.deadline_date >= kst_date(now)))
        if search.province is not None:
            statement = statement.where(V.activity_province == search.province)
        if search.district is not None:
            statement = statement.where(V.activity_district == search.district)
        if search.activity_type is not None:
            statement = statement.where(V.activity_type == search.activity_type)
        if search.q is not None:
            # LIKE 메타문자도 검색어의 글자 그대로다. 인자는 SQLAlchemy가 별도로 바인딩한다.
            escaped = search.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = "%" + escaped + "%"
            role_values = (func.jsonb_array_elements_text(V.role_tags).table_valued("value") if dialect == "postgresql" else func.json_each(V.role_tags).table_valued("key", "value"))
            role_name = exists(select(1).select_from(RoleDefinition).join(role_values, RoleDefinition.id == role_values.c.value).where(RoleDefinition.name.ilike(pattern, escape="\\")))
            statement = statement.where(or_(V.title.ilike(pattern, escape="\\"), V.organization_name.ilike(pattern, escape="\\"), V.description_text.ilike(pattern, escape="\\"), self._tag_matches(V.role_tags, pattern, dialect), self._tag_matches(V.skill_tags, pattern, dialect), role_name))
        return statement

    @staticmethod
    def _public(row, now):
        content = {name: row[name] for name in OpportunityContent.model_fields if name != "activity_region"}
        content["activity_region"] = None if row["activity_province"] is None else {"province": row["activity_province"], "district": row["activity_district"]}
        parsed = OpportunityContent.model_validate(content)
        lifecycle = assess_lifecycle(parsed, source_checked_at=row["source_checked_at"], now=now)
        return PublicOpportunity(**{**parsed.model_dump(), "recruitment_status": lifecycle.recruitment_status}, id=row["opportunity_id"], version=row["version"], description_truncated=row["description_truncated"], source_checked_at=row["source_checked_at"], reviewed_at=row["reviewed_at"], change_pending=row["change_pending"])

    def list(self, search: OpportunitySearch, now: datetime) -> OpportunityPage:
        try:
            with self.connect() as db:
                statement = self._search(self._base(), search, now, db.dialect.name)
                total = db.scalar(select(func.count()).select_from(statement.subquery()))
                offset = (search.page - 1) * search.page_size
                if offset >= total:
                    rows = []
                else:
                    precise_date = cast(func.timezone("Asia/Seoul", V.deadline_at), Date) if db.dialect.name == "postgresql" else func.date(V.deadline_at, "+9 hours")
                    date_order = case((V.deadline_date.is_not(None), V.deadline_date), else_=precise_date)
                    rows = db.execute(statement.order_by(date_order.asc().nulls_last(), V.deadline_at.asc().nulls_last(), V.opportunity_id.asc()).offset(offset).limit(search.page_size)).mappings().all()
                fields = set(OpportunitySummary.model_fields)
                items = [OpportunitySummary.model_validate(self._public(row, now).model_dump(include=fields)) for row in rows]
                return OpportunityPage(items=items, total=total, page=search.page, page_size=search.page_size)
        except (SQLAlchemyError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    def get(self, opportunity_id: UUID, now: datetime) -> PublicOpportunity | None:
        try:
            with self.connect() as db:
                row = db.execute(self._base().where(V.opportunity_id == opportunity_id)).mappings().one_or_none()
                return None if row is None else self._public(row, now)
        except (SQLAlchemyError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None
