"""검수 상태 전이를 공고 문서 행 잠금 안에서 처리한다. 수집 저장소와 같은 문서 잠금을 쓴다."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.core.business_errors import AppError
from app.modules.opportunities.versions import snapshot_from_row
from app.modules.opportunity_reviews.models import ReviewCommand, ReviewResult
from app.modules.opportunity_reviews.service import Check
from app.persistence.operations import (
    AUDIT_RETENTION, AuditEvent, OpportunityDocument as D, OpportunityPublication as P, OpportunityReview as R, OpportunityVersion as V,
)

_STATUS = {"approve": "approved", "reject": "rejected", "hide": "hidden"}


class SqlOpportunityReviewRepository:
    def __init__(self, transaction):
        self.transaction = transaction

    def apply(self, opportunity_id: UUID, command: ReviewCommand, check: Check | None = None) -> ReviewResult:
        try:
            with self.transaction() as db:
                # 같은 공고의 수집 버전 추가·다른 운영자 결정과 직렬화한다.
                if db.scalar(select(D.id).where(D.id == opportunity_id).with_for_update()) is None:
                    raise AppError("NOT_FOUND")
                target = db.execute(select(V.__table__).where(
                    V.opportunity_id == opportunity_id, V.version == command.base_version)).mappings().one_or_none()
                if target is None:
                    raise AppError("VERSION_CONFLICT")
                if command.action in ("approve", "reject"):
                    result = self._review(db, opportunity_id, target, command, check)
                else:
                    result = self._withdraw(db, opportunity_id, target, command)
                db.execute(insert(R), {"opportunity_id": opportunity_id, "version": command.base_version,
                                       "action": command.action, "reason_code": command.reason_code, "note": command.note,
                                       "request_id": command.request_id, "at": command.at})
                db.execute(insert(AuditEvent), {"at": command.at, "actor_id": command.actor_id, "actor_role": "operator",
                                                "action": "opportunity." + command.action, "target_type": "opportunity",
                                                "target_id": opportunity_id, "result": "success",
                                                "request_id": command.request_id, "expires_at": command.at + AUDIT_RETENTION})
                return result
        except (SQLAlchemyError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    @staticmethod
    def _review(db, opportunity_id, target, command, check):
        latest = db.scalar(select(func.max(V.version)).where(V.opportunity_id == opportunity_id))
        if command.base_version != latest:
            raise AppError("VERSION_CONFLICT")
        if target["review_status"] != "pending":
            raise AppError("INVALID_STATE_TRANSITION")
        if check is not None:
            check(snapshot_from_row(target), command.at)
        status = _STATUS[command.action]
        changed = db.execute(update(V).where(
            V.opportunity_id == opportunity_id, V.version == command.base_version, V.review_status == "pending",
        ).values(review_status=status, reviewed_at=command.at)).rowcount
        if changed != 1:
            raise AppError("VERSION_CONFLICT")
        if command.action == "approve":
            # 승인한 버전이 공개본이 된다. 포인터 FK는 승인 상태의 버전만 받는다.
            if db.scalar(select(P.version).where(P.opportunity_id == opportunity_id).with_for_update()) is None:
                db.execute(insert(P), {"opportunity_id": opportunity_id, "version": command.base_version})
            else:
                db.execute(update(P).where(P.opportunity_id == opportunity_id).values(version=command.base_version))
        return ReviewResult(id=opportunity_id, version=command.base_version, review_status=status, reviewed_at=command.at)

    @staticmethod
    def _withdraw(db, opportunity_id, target, command):
        public = db.scalar(select(P.version).where(P.opportunity_id == opportunity_id).with_for_update())
        if public is None:
            raise AppError("INVALID_STATE_TRANSITION")
        if public != command.base_version:
            raise AppError("VERSION_CONFLICT")
        if command.action == "hide":
            # 공개 포인터를 먼저 지워야 승인 상태를 바꿀 수 있다. 저장 지원서는 읽을 때 종료 재검토 표시가 붙는다.
            db.execute(delete(P).where(P.opportunity_id == opportunity_id))
            db.execute(update(V).where(V.opportunity_id == opportunity_id, V.version == command.base_version)
                       .values(review_status="hidden", reviewed_at=command.at))
            return ReviewResult(id=opportunity_id, version=command.base_version, review_status="hidden", reviewed_at=command.at)
        if target["recruitment_status"] == "closed":
            raise AppError("INVALID_STATE_TRANSITION")
        # 닫는 방향이라 재검수 없이 반영한다. 본문·해시·검수 시각은 바꾸지 않는다.
        db.execute(update(V).where(
            V.opportunity_id == opportunity_id,
            or_(V.version == command.base_version, (V.version > command.base_version) & (V.review_status == "pending")),
        ).values(recruitment_status="closed"))
        return ReviewResult(id=opportunity_id, version=command.base_version, review_status=target["review_status"],
                            reviewed_at=target["reviewed_at"])
