"""같은 User 행 잠금/트랜잭션 안의 저장·응답 기록. 본문은 암호문만 저장한다."""

from datetime import timedelta
import json
from uuid import uuid4

from app.contracts.profile import ProfileContent
from app.contracts.saved_profiles import ProfileSaveResult, SavedProfile
from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.core.encryption import ContentTarget, EncryptedEnvelope, EncryptionUnavailable, ProtectedContentError
from app.persistence import ProfileDocument, ProfileVersion, ProfileWriteReceipt
from pydantic import ValidationError
from sqlalchemy import delete, select


class SqlProfileRepository:
    def __init__(self, cipher):
        self.cipher = cipher

    def require_cipher(self):
        if self.cipher is None:
            raise AppError('SERVICE_UNAVAILABLE')

    @staticmethod
    def current(db, owner_id):
        return db.scalar(select(ProfileVersion).where(ProfileVersion.owner_id == owner_id).order_by(ProfileVersion.version.desc()).limit(1))

    def content(self, row):
        self.require_cipher()
        try:
            envelope = EncryptedEnvelope(row.ciphertext, row.nonce, row.key_id, row.algorithm, row.schema_version)
            raw = self.cipher.decrypt(envelope, ContentTarget(row.owner_id, 'profile', row.profile_id, row.version, row.schema_version))
            return ProfileContent.model_validate_json(raw)
        except (EncryptionUnavailable, ProtectedContentError, ValidationError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    def view(self, db, owner_id):
        row = self.current(db, owner_id)
        if row is None:
            return None
        return SavedProfile(profile_id=row.profile_id, version=row.version, confirmed_at=row.confirmed_at,
                            saved_at=row.saved_at, content=self.content(row))

    def replay(self, db, owner_id, key, fingerprint):
        now = utc_now()
        db.execute(delete(ProfileWriteReceipt).where(ProfileWriteReceipt.owner_id == owner_id, ProfileWriteReceipt.expires_at <= now))
        receipt = db.get(ProfileWriteReceipt, (owner_id, key))
        if receipt is None:
            return None
        if receipt.input_hash != fingerprint:
            raise AppError('IDEMPOTENCY_KEY_REUSED')
        row = db.scalar(select(ProfileVersion).where(ProfileVersion.owner_id == owner_id,
            ProfileVersion.profile_id == receipt.profile_id, ProfileVersion.version == receipt.version))
        if row is None:
            raise AppError('NOT_FOUND')
        return ProfileSaveResult(version=receipt.version, saved_at=receipt.saved_at, created=receipt.created,
                                 replaced_version=receipt.replaced_version)

    @staticmethod
    def check_base(db, owner_id, base):
        current = SqlProfileRepository.current(db, owner_id)
        if (current.version if current else None) != base:
            raise AppError('VERSION_CONFLICT')

    def write(self, db, account, approved, key, fingerprint):
        self.require_cipher()
        current = self.current(db, account.id)
        same = current is not None and self.content(current) == approved.profile
        now = utc_now()
        if same:
            row = current
        else:
            document = db.scalar(select(ProfileDocument).where(ProfileDocument.owner_id == account.id))
            if document is None:
                document = ProfileDocument(id=uuid4(), owner_id=account.id);db.add(document);db.flush()
            version = current.version + 1 if current else 1
            if version >= 2**31 or approved.confirmed_at > now:
                raise AppError('SERVICE_UNAVAILABLE')
            raw = json.dumps(approved.profile.model_dump(mode='json'), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
            try:
                envelope = self.cipher.encrypt(raw, ContentTarget(account.id, 'profile', document.id, version, 1))
            except (EncryptionUnavailable, ProtectedContentError):
                raise AppError('SERVICE_UNAVAILABLE') from None
            row = ProfileVersion(profile_id=document.id, owner_id=account.id, version=version, confirmed_at=approved.confirmed_at,
                saved_at=now, ciphertext=envelope.ciphertext, nonce=envelope.nonce, key_id=envelope.key_id,
                algorithm=envelope.algorithm, schema_version=envelope.schema_version)
            db.add(row);db.flush()
        result = ProfileSaveResult(version=row.version, saved_at=row.saved_at, created=not same,
                                   replaced_version=current.version if current and not same else None)
        db.add(ProfileWriteReceipt(owner_id=account.id, key_id=key, input_hash=fingerprint, profile_id=row.profile_id,
            version=result.version, saved_at=result.saved_at, created=result.created, replaced_version=result.replaced_version,
            recorded_at=now, expires_at=now + timedelta(hours=24)))
        db.flush()
        return result
