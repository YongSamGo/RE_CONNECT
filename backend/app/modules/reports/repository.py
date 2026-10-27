"""신고 저장·운영자 처리·보관 정리. 설명·처리 사유는 암호화 봉투로만 읽고 쓴다.

처리와 감사 기록은 같은 트랜잭션이다. 감사 기록에는 누가·무엇을·언제만 두고 사유 원문은 넣지 않는다.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.engine import Connection

from app.contracts.preparation import OpportunityRef
from app.core.business_errors import AppError
from app.core.encryption import ContentCipher, ContentTarget, EncryptedEnvelope, ALGORITHM, EncryptionUnavailable, ProtectedContentError
from app.modules.reports.models import TERMINAL, TRANSITIONS, AdminReport, AdminReportList, ReportCreate, ReportUpdate
from app.persistence.operations import AuditEvent, OpportunityVersion as V, Report as R

AUDIT_RETENTION = timedelta(days=30)
DETAIL_RETENTION = timedelta(days=30)
SCHEMA_VERSION = 1
# 신고 설명은 접수 버전(1)에, 처리 사유는 그 사유를 쓴 처리 버전(2 이상)에 묶는다.
# 두 칸의 암호문을 서로 바꿔 넣으면 복호화가 실패한다.
NOTE_VERSION = 1


def _target(opportunity_id: UUID, report_id: UUID, version: int) -> ContentTarget:
    return ContentTarget(owner_id=opportunity_id, kind="report", document_id=report_id, version=version, schema_version=SCHEMA_VERSION)


class SqlReportRepository:
    def __init__(self, transaction: Callable[[], AbstractContextManager[Connection]], cipher: ContentCipher | None):
        self.transaction = transaction
        self.cipher = cipher

    def _require_cipher(self) -> ContentCipher:
        if self.cipher is None:
            raise AppError("SERVICE_UNAVAILABLE")
        return self.cipher

    def _seal(self, text: str | None, target: ContentTarget) -> dict:
        if text is None:
            return {"ciphertext": None, "nonce": None, "key_id": None}
        envelope = self._require_cipher().encrypt(text.encode("utf-8"), target)
        return {"ciphertext": envelope.ciphertext, "nonce": envelope.nonce, "key_id": envelope.key_id}

    def _open(self, ciphertext, nonce, key_id, target: ContentTarget) -> str | None:
        if ciphertext is None:
            return None
        envelope = EncryptedEnvelope(bytes(ciphertext), bytes(nonce), key_id, ALGORITHM, SCHEMA_VERSION)
        return self._require_cipher().decrypt(envelope, target).decode("utf-8")

    def exists(self, report_id: UUID) -> bool:
        try:
            with self.transaction() as db:
                return db.scalar(select(R.id).where(R.id == report_id)) is not None
        except SQLAlchemyError:
            raise AppError("SERVICE_UNAVAILABLE") from None

    def create(self, report_id: UUID, received_at: datetime, body: ReportCreate) -> None:
        """같은 신고 ID는 한 번만 저장한다. 응답 유실 뒤 재시도는 기존 행을 그대로 둔다."""
        self._require_cipher()  # 설명이 없어도 같은 설정에서만 접수해 목록 조회와 어긋나지 않게 한다.
        try:
            note = self._seal(body.note, _target(body.opportunity.id, report_id, NOTE_VERSION))
            with self.transaction() as db:
                if db.scalar(select(R.id).where(R.id == report_id)) is not None:
                    return
                db.execute(insert(R), {
                    "id": report_id, "opportunity_id": body.opportunity.id, "opportunity_version": body.opportunity.version,
                    "type": body.type, "status": "received", "version": 1, "received_at": received_at, "updated_at": received_at,
                    "details_ciphertext": note["ciphertext"], "details_nonce": note["nonce"], "details_key_id": note["key_id"],
                })
        except IntegrityError:
            # 동시에 같은 재시도가 먼저 저장했으면 성공으로 본다. 그 밖의 제약 위반은 서버 오류다.
            if not self.exists(report_id):
                raise AppError("SERVICE_UNAVAILABLE") from None
        except (SQLAlchemyError, EncryptionUnavailable, ProtectedContentError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    @staticmethod
    def _columns():
        return select(R.__table__, V.title.label("opportunity_title")).join(
            V, (V.opportunity_id == R.opportunity_id) & (V.version == R.opportunity_version))

    def _admin(self, row) -> AdminReport:
        return AdminReport(
            report_id=row["id"], version=row["version"],
            opportunity=OpportunityRef(id=row["opportunity_id"], version=row["opportunity_version"]),
            opportunity_title=row["opportunity_title"], type=row["type"], status=row["status"],
            note=self._open(row["details_ciphertext"], row["details_nonce"], row["details_key_id"],
                            _target(row["opportunity_id"], row["id"], NOTE_VERSION)),
            resolution_note=self._open(row["resolution_ciphertext"], row["resolution_nonce"], row["resolution_key_id"],
                                       _target(row["opportunity_id"], row["id"], row["version"])),
            created_at=row["received_at"], updated_at=row["updated_at"],
        )

    def listing(self, status: str | None, page: int, page_size: int) -> AdminReportList:
        self._require_cipher()
        try:
            with self.transaction() as db:
                condition = [] if status is None else [R.status == status]
                total = db.scalar(select(func.count()).select_from(R).where(*condition))
                offset = (page - 1) * page_size
                rows = [] if offset >= total else db.execute(
                    # 오래 기다린 신고부터 본다. 뒤쪽 페이지로 밀려 처리되지 않는 신고가 생기지 않게 한다.
                    self._columns().where(*condition).order_by(R.received_at.asc(), R.id.asc()).offset(offset).limit(page_size)
                ).mappings().all()
                return AdminReportList(items=[self._admin(row) for row in rows], page=page, page_size=page_size, total=total)
        except (SQLAlchemyError, ValidationError, EncryptionUnavailable, ProtectedContentError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    def update(self, report_id: UUID, body: ReportUpdate, *, actor_id: UUID, request_id: str, at: datetime) -> AdminReport:
        self._require_cipher()
        try:
            with self.transaction() as db:
                row = db.execute(self._columns().where(R.id == report_id).with_for_update(of=R.__table__)).mappings().one_or_none()
                if row is None:
                    raise AppError("NOT_FOUND")
                if row["version"] != body.base_version:
                    raise AppError("VERSION_CONFLICT")
                if body.status not in TRANSITIONS.get(row["status"], frozenset()):
                    raise AppError("INVALID_STATE_TRANSITION")
                version = row["version"] + 1
                updated_at = max(at, row["updated_at"])
                resolution = self._seal(body.resolution_note, _target(row["opportunity_id"], report_id, version))
                changed = db.execute(update(R).where(R.id == report_id, R.version == row["version"], R.status == row["status"]).values(
                    status=body.status, version=version, updated_at=updated_at, resolution_ciphertext=resolution["ciphertext"],
                    resolution_nonce=resolution["nonce"], resolution_key_id=resolution["key_id"])).rowcount
                if changed != 1:
                    raise AppError("VERSION_CONFLICT")
                db.execute(insert(AuditEvent), {"at": at, "actor_id": actor_id, "actor_role": "operator", "action": "report.update",
                                                "target_type": "report", "target_id": report_id, "result": "success",
                                                "request_id": request_id, "expires_at": at + AUDIT_RETENTION})
                return self._admin({**row, "status": body.status, "version": version, "updated_at": updated_at,
                                    "resolution_ciphertext": resolution["ciphertext"], "resolution_nonce": resolution["nonce"],
                                    "resolution_key_id": resolution["key_id"]})
        except (SQLAlchemyError, ValidationError, EncryptionUnavailable, ProtectedContentError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    def purge(self, now: datetime, limit: int) -> int:
        """종결 후 30일이 지난 신고의 설명·처리 사유를 지운다. 유형·상태·대상 공고는 남긴다."""
        try:
            with self.transaction() as db:
                ids = db.scalars(select(R.id).where(R.status.in_(TERMINAL), R.purged_at.is_(None), R.updated_at <= now - DETAIL_RETENTION)
                                 .order_by(R.updated_at, R.id).limit(limit)).all()
                if not ids:
                    return 0
                return db.execute(update(R).where(R.id.in_(ids), R.purged_at.is_(None)).values(
                    details_ciphertext=None, details_nonce=None, details_key_id=None,
                    resolution_ciphertext=None, resolution_nonce=None, resolution_key_id=None, purged_at=now)).rowcount
        except SQLAlchemyError:
            raise AppError("SERVICE_UNAVAILABLE") from None


class UnavailableReportRepository:
    def exists(self, *args, **kwargs):
        raise AppError("SERVICE_UNAVAILABLE")

    create = listing = update = purge = exists
