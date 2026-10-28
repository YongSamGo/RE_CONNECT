"""운영자 역할·MFA 비밀값의 DB 접근과 감사 기록 (W07-01).

OTP 확인은 계정 행을 잠근 한 트랜잭션에서 잠금 확인 → 비교 → 재사용 검사 → 실패/성공 기록을 함께 한다.
비밀값은 #25 AES-GCM으로 계정·자격 ID에 묶어 저장하고, 평문·OTP는 반환값 외에 남기지 않는다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import delete, exists, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.core.business_errors import AppError
from app.core.encryption import ContentTarget, EncryptedEnvelope, EncryptionUnavailable, ProtectedContentError
from app.modules.operators import totp
from app.persistence.members import OperatorMfaCredential, User
from app.persistence.operations import AUDIT_RETENTION, AuditEvent, DeletionRecord

FAILURE_LIMIT = 5
# 잠길 때마다 길어진다(15분 → 1시간 → 24시간). 성공하면 처음으로 돌아간다.
LOCK_STEPS_SECONDS = (15 * 60, 60 * 60, 24 * 60 * 60)
LOCK_SECONDS = LOCK_STEPS_SECONDS[0]
# 연속 10번 잠기면(연속 실패 50회) reset-mfa 전까지 막는다. 장기 추측 성공 확률을 약 1.5e-4 이하로 묶는다.
BLOCK_AFTER_LOCKS = 10
_MAX_GENERATION = 2147483646


@dataclass(frozen=True)
class VerifyResult:
    status: Literal["verified", "invalid", "locked", "blocked", "forbidden"]
    credential_id: UUID | None = None
    retry_after: int | None = None


class OperatorProcedureError(Exception):
    """관리 절차 거절. 코드만 담고 사용자 식별값·비밀값은 넣지 않는다."""

    def __init__(self, code: Literal["not_found", "not_operator", "already_operator", "already_enrolled",
                                     "not_enrolled", "pending_deletion", "unavailable"]):
        self.code = code
        super().__init__(code)


def _target(user_id: UUID, credential_id: UUID) -> ContentTarget:
    return ContentTarget(owner_id=user_id, kind="operator_mfa", document_id=credential_id, version=1, schema_version=1)


def _audit(db, *, now, action, actor_id, actor_role, result, request_id, target_id):
    db.execute(insert(AuditEvent).values(
        id=uuid4(), at=now, actor_id=actor_id, actor_role=actor_role, action=action, target_type="user",
        target_id=target_id, result=result, request_id=request_id, expires_at=now + AUDIT_RETENTION))


class SqlOperatorMfaRepository:
    def __init__(self, transaction, cipher):
        self.transaction, self.cipher = transaction, cipher

    @staticmethod
    def _limits(db):
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET LOCAL statement_timeout = 5000"))
            db.execute(text("SET LOCAL lock_timeout = 1000"))

    @staticmethod
    def _operator(db, user_id, *, lock=False):
        statement = select(User.role, User.status, User.session_generation).where(User.id == user_id)
        row = db.execute(statement.with_for_update() if lock else statement).one_or_none()
        if row is None or row.status != "active":
            return None
        pending = db.scalar(select(exists().where(DeletionRecord.owner_id == user_id, DeletionRecord.status.in_(["pending", "failed"]))))
        return None if pending else row

    def credential_id(self, user_id: UUID) -> UUID | None:
        """현재 유효한 MFA 자격 ID. 역할 회수·정지·삭제 진행·재등록이면 없음/다른 값이 된다.

        관리 API마다 부르므로 역할·상태·삭제 기록·자격을 한 쿼리로 읽는다.
        """
        pending = exists().where(DeletionRecord.owner_id == User.id, DeletionRecord.status.in_(["pending", "failed"]))
        statement = (select(OperatorMfaCredential.credential_id)
                     .join(User, User.id == OperatorMfaCredential.user_id)
                     .where(User.id == user_id, User.role == "admin", User.status == "active", ~pending))
        try:
            with self.transaction() as db:
                self._limits(db)
                return db.scalar(statement)
        except SQLAlchemyError:
            raise AppError("SERVICE_UNAVAILABLE") from None

    def verify(self, user_id: UUID, otp: str, now: datetime, request_id: str) -> VerifyResult:
        try:
            with self.transaction() as db:
                self._limits(db)
                row = self._operator(db, user_id, lock=True)
                if row is None or row.role != "admin":
                    return VerifyResult("forbidden")
                credential = db.execute(select(OperatorMfaCredential).where(OperatorMfaCredential.user_id == user_id)
                                        .with_for_update()).scalar_one_or_none()
                audit = dict(now=now, actor_id=user_id, actor_role="operator", request_id=request_id, target_id=user_id)
                if credential is None:
                    # 비교할 비밀값이 없다. 등록 전 시도는 denied로 구분하고 15분에 한 번만 남겨 감사 기록이 쌓이지 않게 한다.
                    recent = exists().where(AuditEvent.actor_id == user_id, AuditEvent.action == "mfa.fail",
                                            AuditEvent.result == "denied", AuditEvent.at > now - timedelta(seconds=LOCK_SECONDS))
                    if not db.scalar(select(recent)):
                        _audit(db, action="mfa.fail", result="denied", **audit)
                    return VerifyResult("invalid")
                if credential.lock_count >= BLOCK_AFTER_LOCKS:
                    # reset-mfa로 다시 등록하기 전까지 OTP를 비교하지 않는다.
                    return VerifyResult("blocked", retry_after=LOCK_STEPS_SECONDS[-1])
                if credential.locked_until is not None and credential.locked_until > now:
                    # 잠금 중에는 OTP를 비교하지 않는다.
                    return VerifyResult("locked", retry_after=max(1, math.ceil((credential.locked_until - now).total_seconds())))
                secret = self._secret(credential)
                step = totp.matching_step(secret, otp, totp.time_step(now.timestamp()))
                if step is not None and (credential.last_step is None or step > credential.last_step):
                    credential.last_step, credential.failed_count, credential.locked_until = step, 0, None
                    credential.lock_count = 0
                    _audit(db, action="mfa.verify", result="success", **audit)
                    return VerifyResult("verified", credential.credential_id)
                # 틀린 OTP와 이미 쓴 OTP를 같은 실패로 센다.
                _audit(db, action="mfa.fail", result="failed", **audit)
                if credential.failed_count + 1 >= FAILURE_LIMIT:
                    seconds = LOCK_STEPS_SECONDS[min(credential.lock_count, len(LOCK_STEPS_SECONDS) - 1)]
                    credential.lock_count += 1
                    credential.failed_count, credential.locked_until = 0, now + timedelta(seconds=seconds)
                    _audit(db, action="mfa.lock", result="denied", **audit)
                    if credential.lock_count >= BLOCK_AFTER_LOCKS:
                        return VerifyResult("blocked", retry_after=LOCK_STEPS_SECONDS[-1])
                    return VerifyResult("locked", retry_after=seconds)
                credential.failed_count += 1
                return VerifyResult("invalid")
        except (SQLAlchemyError, ProtectedContentError, EncryptionUnavailable):
            raise AppError("SERVICE_UNAVAILABLE") from None

    def _secret(self, credential) -> bytes:
        envelope = EncryptedEnvelope(credential.ciphertext, credential.nonce, credential.key_id, credential.algorithm,
                                     credential.schema_version)
        return self.cipher.decrypt(envelope, _target(credential.user_id, credential.credential_id))

    # ---- 앱 밖 관리 절차(manage_operators.py) 전용. 공개 API로 열지 않는다. ----

    def _procedure(self, work):
        try:
            with self.transaction() as db:
                self._limits(db)
                return work(db)
        except OperatorProcedureError:
            raise
        except (SQLAlchemyError, ProtectedContentError, EncryptionUnavailable):
            raise OperatorProcedureError("unavailable") from None

    def _locked_operator(self, db, user_id):
        row = db.execute(select(User.role, User.status, User.session_generation).where(User.id == user_id).with_for_update()).one_or_none()
        if row is None or row.status != "active":
            raise OperatorProcedureError("not_found")
        if db.scalar(select(exists().where(DeletionRecord.owner_id == user_id, DeletionRecord.status.in_(["pending", "failed"])))):
            raise OperatorProcedureError("pending_deletion")
        return row

    @staticmethod
    def _expire_sessions(db, user_id, row):
        # 세대가 바뀌면 모든 회원 세션이 다음 요청에서 SESSION_EXPIRED가 된다.
        if row.session_generation >= _MAX_GENERATION:
            raise OperatorProcedureError("unavailable")
        db.execute(update(User).where(User.id == user_id).values(session_generation=row.session_generation + 1))

    def grant(self, user_id: UUID, *, now: datetime, request_id: str) -> None:
        def work(db):
            row = self._locked_operator(db, user_id)
            if row.role == "admin":
                raise OperatorProcedureError("already_operator")
            db.execute(update(User).where(User.id == user_id).values(role="admin"))
            _audit(db, now=now, action="role.grant", actor_id=None, actor_role="system", result="success",
                   request_id=request_id, target_id=user_id)
        self._procedure(work)

    def revoke(self, user_id: UUID, *, now: datetime, request_id: str) -> None:
        def work(db):
            row = self._locked_operator(db, user_id)
            if row.role != "admin":
                raise OperatorProcedureError("not_operator")
            db.execute(delete(OperatorMfaCredential).where(OperatorMfaCredential.user_id == user_id))
            db.execute(update(User).where(User.id == user_id).values(role="user"))
            self._expire_sessions(db, user_id, row)
            _audit(db, now=now, action="role.revoke", actor_id=None, actor_role="system", result="success",
                   request_id=request_id, target_id=user_id)
        self._procedure(work)

    def check_enrollable(self, user_id: UUID) -> None:
        """비밀값을 만들기 전 읽기 전용 사전 확인. 저장 시점의 같은 확인은 경합 방지로 남긴다."""
        def work(db):
            row = self._operator(db, user_id)
            if row is None:
                pending = db.scalar(select(exists().where(DeletionRecord.owner_id == user_id,
                                                           DeletionRecord.status.in_(["pending", "failed"]))))
                raise OperatorProcedureError("pending_deletion" if pending else "not_found")
            if row.role != "admin":
                raise OperatorProcedureError("not_operator")
            if db.scalar(select(exists().where(OperatorMfaCredential.user_id == user_id))):
                raise OperatorProcedureError("already_enrolled")
        self._procedure(work)

    def enroll(self, user_id: UUID, secret: bytes, confirmed_step: int, *, now: datetime, request_id: str) -> UUID:
        """관리자가 인증 앱의 첫 코드를 확인한 비밀값만 저장한다. 그 코드는 다시 쓸 수 없다."""
        if type(secret) is not bytes or len(secret) != totp.SECRET_BYTES or type(confirmed_step) is not int or confirmed_step <= 0:
            raise OperatorProcedureError("unavailable")

        def work(db):
            row = self._locked_operator(db, user_id)
            if row.role != "admin":
                raise OperatorProcedureError("not_operator")
            if db.scalar(select(exists().where(OperatorMfaCredential.user_id == user_id))):
                raise OperatorProcedureError("already_enrolled")
            credential_id = uuid4()
            envelope = self.cipher.encrypt(secret, _target(user_id, credential_id))
            db.execute(insert(OperatorMfaCredential).values(
                user_id=user_id, credential_id=credential_id, last_step=confirmed_step, failed_count=0, lock_count=0, locked_until=None,
                enrolled_at=now, ciphertext=envelope.ciphertext, nonce=envelope.nonce, key_id=envelope.key_id,
                algorithm=envelope.algorithm, schema_version=envelope.schema_version))
            _audit(db, now=now, action="mfa.enroll", actor_id=None, actor_role="system", result="success",
                   request_id=request_id, target_id=user_id)
            return credential_id
        return self._procedure(work)

    def reset(self, user_id: UUID, *, now: datetime, request_id: str) -> None:
        """기기 분실 복구. 기존 비밀값을 지우고 모든 세션을 끊는다. 이후 enroll로 다시 등록한다."""
        def work(db):
            row = self._locked_operator(db, user_id)
            if row.role != "admin":
                raise OperatorProcedureError("not_operator")
            removed = db.execute(delete(OperatorMfaCredential).where(OperatorMfaCredential.user_id == user_id)).rowcount
            if not removed:
                raise OperatorProcedureError("not_enrolled")
            self._expire_sessions(db, user_id, row)
            _audit(db, now=now, action="mfa.reset", actor_id=None, actor_role="system", result="success",
                   request_id=request_id, target_id=user_id)
        self._procedure(work)


class UnavailableOperatorMfaRepository:
    """DB나 암호화 키가 없으면 MFA 확인·관리 API를 모두 닫는다."""

    def credential_id(self, *args, **kwargs):
        raise AppError("SERVICE_UNAVAILABLE")

    verify = credential_id
