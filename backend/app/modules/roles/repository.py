"""운영 역할 사전 조회. 잘못된 저장값을 잘라서 정상 후보로 바꾸지 않는다."""

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.contracts.roles import CatalogRole
from app.core.business_errors import AppError
from app.persistence.operations import RoleDefinition

MAX_CATALOG_ROLES = 500


class SQLRoleCatalog:
    def __init__(self, connect):
        self.connect = connect

    def list(self) -> list[CatalogRole]:
        try:
            with self.connect() as db:
                rows = db.execute(select(*RoleDefinition.__table__.c).order_by(RoleDefinition.id).limit(MAX_CATALOG_ROLES + 1)).mappings().all()
                if len(rows) > MAX_CATALOG_ROLES:
                    raise ValueError
                return [CatalogRole.model_validate(dict(row)) for row in rows]
        except (SQLAlchemyError, ValidationError, ValueError):
            raise AppError("SERVICE_UNAVAILABLE") from None


class UnavailableRoleCatalog:
    def list(self):
        raise AppError("SERVICE_UNAVAILABLE")
