"""운영자 공고 저장 경계. 쓰기는 공고 버전·근거·감사·재전송 기록을 한 트랜잭션으로 커밋한다.

잠금 순서는 수집과 같은 source → document다. 원문을 SQL 구문으로 조립하지 않는다.
"""

from contextlib import contextmanager
from datetime import timedelta
import json

from pydantic import ValidationError
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.contracts.opportunity import OpportunityContent
from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.modules.admin_opportunities.models import (
    AdminOpportunity, AdminOpportunityList, AdminOpportunitySummary, AdminSource,
)
from app.modules.ingestion.manual import ManualInput, ManualIntake, official_url, unsafe_text_fields
from app.modules.opportunities.ingestion import IngestionService
from app.modules.opportunities.ingestion_repository import SqlIngestionRepository, pending_version_values
from app.modules.opportunities.versions import OpportunitySnapshot, changed_fields, important_changes, snapshot_from_row
from app.persistence.operations import (
    AUDIT_RETENTION, AuditEvent, OpportunityDocument as D, OpportunityPublication as P, OpportunityVersion as V,
    OpportunityWriteReceipt as R, RoleDefinition, Source,
)

RECEIPT_RETENTION = timedelta(hours=24)
# 중요 변경 여부는 공개본과 버전들을 비교해 계산하므로 목록을 메모리에서 나눈다. 넘으면 일부만 보여 주지 않고 거절한다.
LIST_LIMIT = 5000
CONTENT_FIELDS = frozenset(OpportunityContent.model_fields)


def _content(snapshot: OpportunitySnapshot) -> OpportunityContent:
    return OpportunityContent.model_validate(snapshot.model_dump(exclude={"description_truncated"}))


def _change_pending(published_version, published, rows) -> bool:
    """공개본 뒤의 검수 대기 버전 중 하나라도 중요 변경이면 공개본 추천을 보류 중이다(공개 조회와 같은 규칙)."""
    if published is None:
        return False
    base = snapshot_from_row(published)
    return any(row["version"] > published_version and row["review_status"] == "pending"
               and important_changes(base, snapshot_from_row(row)) for row in rows)


class SqlAdminOpportunityRepository:
    def __init__(self, transaction, *, clock=utc_now):
        self.transaction, self.clock = transaction, clock

    def _store(self, db):
        @contextmanager
        def transaction():
            yield db
        return IngestionService(SqlIngestionRepository(transaction), clock=self.clock)

    def _pending_flags(self, db) -> dict:
        rows = db.execute(select(V.__table__, P.version.label("published_version"))
                          .join(P, (P.opportunity_id == V.opportunity_id) & (V.version >= P.version))).mappings().all()
        groups: dict = {}
        for row in rows:
            groups.setdefault(row["opportunity_id"], []).append(row)
        flags = {}
        for opportunity_id, versions in groups.items():
            published_version = versions[0]["published_version"]
            published = next(row for row in versions if row["version"] == published_version)
            flags[opportunity_id] = _change_pending(published_version, published, versions)
        return flags

    def list(self, search) -> AdminOpportunityList:
        try:
            with self.transaction() as db:
                ManualIntake._limits(db)
                latest = select(V.opportunity_id, func.max(V.version).label("version")).group_by(V.opportunity_id).subquery()
                statement = (select(V.opportunity_id, V.version, V.title, V.organization_name, V.review_status,
                                    V.recruitment_status, V.source_checked_at, V.created_at, P.version.label("published_version"))
                             .join(latest, (latest.c.opportunity_id == V.opportunity_id) & (latest.c.version == V.version))
                             .outerjoin(P, P.opportunity_id == V.opportunity_id))
                if search.review_status is not None:
                    statement = statement.where(V.review_status == search.review_status)
                if search.recruitment_status is not None:
                    statement = statement.where(V.recruitment_status == search.recruitment_status)
                if search.q is not None:
                    # LIKE 메타문자도 검색어의 글자 그대로다. 인자는 SQLAlchemy가 별도로 바인딩한다.
                    escaped = search.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    pattern = "%" + escaped + "%"
                    statement = statement.where(or_(V.title.ilike(pattern, escape="\\"), V.organization_name.ilike(pattern, escape="\\")))
                rows = db.execute(statement.order_by(V.created_at.desc(), V.opportunity_id).limit(LIST_LIMIT + 1)).mappings().all()
                if len(rows) > LIST_LIMIT:
                    raise AppError("SERVICE_UNAVAILABLE")
                flags = self._pending_flags(db)
                items = [(row, flags.get(row["opportunity_id"], False)) for row in rows]
                if search.important_change is not None:
                    items = [item for item in items if item[1] is search.important_change]
                start = (search.page - 1) * search.page_size
                page = [AdminOpportunitySummary(
                    id=row["opportunity_id"], version=row["version"], title=row["title"], organization_name=row["organization_name"],
                    review_status=row["review_status"], recruitment_status=row["recruitment_status"],
                    published_version=row["published_version"], important_change=important,
                    source_checked_at=row["source_checked_at"], updated_at=row["created_at"],
                ) for row, important in items[start:start + search.page_size]]
                return AdminOpportunityList(items=page, page=search.page, page_size=search.page_size, total=len(items))
        except (SQLAlchemyError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    @staticmethod
    def _view(db, opportunity_id) -> AdminOpportunity | None:
        head = db.execute(select(D.external_id, Source.id.label("source_id"), Source.name)
                          .join(Source, Source.id == D.source_id).where(D.id == opportunity_id)).mappings().one_or_none()
        if head is None:
            return None
        rows = db.execute(select(V.__table__).where(V.opportunity_id == opportunity_id).order_by(V.version)).mappings().all()
        if not rows:
            raise AppError("SERVICE_UNAVAILABLE")
        latest = rows[-1]
        published_version = db.scalar(select(P.version).where(P.opportunity_id == opportunity_id))
        published = next((row for row in rows if row["version"] == published_version), None)
        after = snapshot_from_row(latest)
        before = snapshot_from_row(published) if published is not None else None
        return AdminOpportunity(
            id=opportunity_id, version=latest["version"], review_status=latest["review_status"], published_version=published_version,
            source=AdminSource(source_id=head["source_id"], name=head["name"], external_id=head["external_id"]),
            changed_fields=sorted(changed_fields(before, after) & CONTENT_FIELDS) if before is not None else [],
            important_change=_change_pending(published_version, published, rows),
            content=_content(after), published_content=_content(before) if before is not None else None,
            source_checked_at=latest["source_checked_at"], updated_at=latest["created_at"],
        )

    def get(self, opportunity_id) -> AdminOpportunity | None:
        try:
            with self.transaction() as db:
                ManualIntake._limits(db)
                return self._view(db, opportunity_id)
        except (SQLAlchemyError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    @staticmethod
    def _audit(db, operator_id, action, opportunity_id, request_id, now):
        # 감사 기록에는 공고 본문·입력값을 남기지 않는다. 누가·언제·무엇을·결과만 남긴다.
        db.execute(insert(AuditEvent), {
            "at": now, "actor_id": operator_id, "actor_role": "operator", "action": action,
            "target_type": "opportunity", "target_id": opportunity_id, "result": "success",
            "request_id": request_id, "expires_at": now + AUDIT_RETENTION,
        })

    def create(self, operator_id, key_id, fingerprint, body, request_id) -> AdminOpportunity:
        now = self.clock()
        try:
            with self.transaction() as db:
                ManualIntake._limits(db)
                # 같은 출처의 등록·재전송 확인을 직렬화한다. 같은 키의 동시 요청은 먼저 커밋한 결과를 다시 받는다.
                source_id = db.scalar(select(Source.id).where(Source.code == body.source).with_for_update())
                if source_id is None:
                    raise AppError("VALIDATION_FAILED")
                db.execute(delete(R).where(R.operator_id == operator_id, R.expires_at <= now))
                receipt = db.get(R, (operator_id, key_id))
                if receipt is not None:
                    if receipt.input_hash != fingerprint:
                        raise AppError("IDEMPOTENCY_KEY_REUSED")
                    view = self._view(db, receipt.opportunity_id)
                    if view is None:
                        raise AppError("NOT_FOUND")
                    return view
                try:
                    snapshot = OpportunitySnapshot.model_validate({**body.content.model_dump(), "description_truncated": False})
                    material = ManualInput(source_id=source_id, snapshot=snapshot, evidence=body.evidence)
                except ValidationError:
                    raise AppError("VALIDATION_FAILED") from None
                # 공식 경로·근거·연락처·역할 사전 검사와 중복 후보 409는 수동 입력(#51)과 같은 코드가 맡는다.
                result = ManualIntake(None, self._store, clock=lambda: now).record_in(db, material)
                if result.outcome != "created" or result.version != 1:
                    raise AppError("VERSION_CONFLICT")
                self._audit(db, operator_id, "opportunity.create", result.opportunity_id, request_id, now)
                db.execute(insert(R), {"operator_id": operator_id, "key_id": key_id, "input_hash": fingerprint,
                                       "opportunity_id": result.opportunity_id, "version": result.version,
                                       "recorded_at": now, "expires_at": now + RECEIPT_RETENTION})
                return self._view(db, result.opportunity_id)
        except IntegrityError:
            raise AppError("VERSION_CONFLICT") from None
        except (SQLAlchemyError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    def update(self, operator_id, opportunity_id, patch, request_id) -> AdminOpportunity:
        now = self.clock()
        try:
            with self.transaction() as db:
                ManualIntake._limits(db)
                source_id = db.scalar(select(D.source_id).where(D.id == opportunity_id))
                if source_id is None:
                    raise AppError("NOT_FOUND")
                db.execute(select(Source.id).where(Source.id == source_id).with_for_update())
                db.execute(select(D.id).where(D.id == opportunity_id).with_for_update())
                latest = db.execute(select(V.__table__).where(V.opportunity_id == opportunity_id)
                                    .order_by(V.version.desc()).limit(1)).mappings().one_or_none()
                if latest is None:
                    raise AppError("SERVICE_UNAVAILABLE")
                # 기준 버전이 최신이 아니면 다른 수정·수집을 덮어쓰지 않는다.
                if latest["version"] != patch.base_version:
                    raise AppError("VERSION_CONFLICT")
                before = snapshot_from_row(latest)
                merged = {**before.model_dump(mode="json"), **patch.changes}
                if "description_text" in patch.changes:
                    merged["description_truncated"] = False  # 운영자가 직접 적은 설명은 잘린 원문이 아니다.
                try:
                    after = OpportunitySnapshot.model_validate_json(json.dumps(merged, ensure_ascii=False, allow_nan=False))
                    changes = changed_fields(before, after)
                    for field in {"source_url", "application_url"} & changes:
                        official_url(getattr(after, field))
                except (ValidationError, ValueError, TypeError):
                    raise AppError("VALIDATION_FAILED") from None
                # 바뀐 필드만 수동 입력과 같은 일반 텍스트 규칙으로 검사한다. 이전 수집본의 다른 필드로 수정을 막지 않는다.
                if not changes or unsafe_text_fields(after, changes):
                    raise AppError("VALIDATION_FAILED")
                roles = set(after.role_tags)
                if "role_tags" in changes and roles and set(db.scalars(select(RoleDefinition.id).where(RoleDefinition.id.in_(roles)))) != roles:
                    raise AppError("VALIDATION_FAILED")
                # 공고 출처를 다시 확인한 것이 아니므로 기준 버전의 출처 확인 시각과 원문 관측 해시를 그대로 둔다.
                # 같은 원문을 다시 수집하면 이 수정본을 되돌리지 않는다.
                db.execute(insert(V), pending_version_values(after, latest["source_checked_at"], opportunity_id, latest["version"] + 1,
                                                             observed_hash=latest["observed_hash"]))
                self._audit(db, operator_id, "opportunity.update", opportunity_id, request_id, now)
                return self._view(db, opportunity_id)
        except IntegrityError:
            raise AppError("VERSION_CONFLICT") from None
        except (SQLAlchemyError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None


class UnavailableAdminOpportunityRepository:
    def list(self, *args, **kwargs):
        raise AppError("SERVICE_UNAVAILABLE")

    get = create = update = list
