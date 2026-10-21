"""User 행 잠금 안의 근거 연결·공고 검사·암호문과 응답 기록 저장."""

from datetime import timedelta
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import delete, exists, func, or_, select

from app.contracts.saved_drafts import DraftSaveResult, SavedDraft, SavedDraftBody, SavedDraftList, SavedDraftSummary
from app.contracts.time import utc_now
from app.contracts.journey import SavedProfileRef
from app.contracts.preparation import OpportunityRef
from app.core.business_errors import AppError
from app.core.encryption import ContentTarget, EncryptedEnvelope, EncryptionUnavailable, ProtectedContentError
from app.modules.opportunities.lifecycle import assess_lifecycle
from app.modules.opportunities.versions import IMPORTANT_FIELDS, IMPORTANT_STATUS_TRANSITIONS, snapshot_from_row
from app.persistence import ApplicationDocument, ApplicationDraft, ApplicationWriteReceipt, ProfileVersion
from app.modules.saved_drafts.service import StoredDraftEditSource
from app.persistence.operations import OpportunityPublication as P, OpportunityVersion as V


class SqlDraftRepository:
    def __init__(self, profiles):
        self.profiles = profiles

    @staticmethod
    def _snapshot(row):
        try:
            return snapshot_from_row({column.name: getattr(row, column.name) for column in V.__table__.columns})
        except ValidationError:
            raise AppError('SERVICE_UNAVAILABLE') from None

    @staticmethod
    def _pending(db, row):
        pending = V.__table__.alias('pending_draft')
        columns = (set(IMPORTANT_FIELDS) - {'activity_region'}) | {'activity_province', 'activity_district'}
        changes = [pending.c[name].is_distinct_from(getattr(row, name)) for name in sorted(columns)]
        changes += [pending.c.recruitment_status == after for before, after in IMPORTANT_STATUS_TRANSITIONS if row.recruitment_status == before]
        changes.append(pending.c.recruitment_status == 'closed')
        return db.scalar(select(exists(select(1).where(pending.c.opportunity_id == row.opportunity_id,
            pending.c.version > row.version, pending.c.review_status == 'pending', or_(*changes)))))

    def opportunity(self, db, reference):
        publication = db.scalar(select(P).where(P.opportunity_id == reference.id).with_for_update(read=True))
        row = db.scalar(select(V).where(V.opportunity_id == reference.id, V.version == reference.version).with_for_update(read=True))
        if publication is None or publication.review_status != 'approved' or publication.version != reference.version or row is None or row.review_status != 'approved':
            raise AppError('OPPORTUNITY_NOT_AVAILABLE')
        if self._pending(db, row) or not assess_lifecycle(self._snapshot(row), source_checked_at=row.source_checked_at, now=utc_now()).recommendation_allowed:
            raise AppError('OPPORTUNITY_NOT_AVAILABLE')

    def profile(self, db, owner_id, approved):
        row = self.profiles.current(db, owner_id)
        if row is None or self.profiles.content(row) != approved.profile:
            raise AppError('PROFILE_NOT_SAVED')
        return row

    @staticmethod
    def current(db, owner_id, document_id):
        return db.scalar(select(ApplicationDraft).where(ApplicationDraft.owner_id == owner_id,
            ApplicationDraft.document_id == document_id).order_by(ApplicationDraft.version.desc()).limit(1))

    def document(self, db, owner_id, body, profile):
        if body.document_id is None:
            return None
        document = db.scalar(select(ApplicationDocument).where(ApplicationDocument.owner_id == owner_id, ApplicationDocument.id == body.document_id))
        if document is None:
            raise AppError('NOT_FOUND')
        row = self.current(db, owner_id, document.id)
        if row is None or row.version != body.base_document_version:
            raise AppError('VERSION_CONFLICT')
        if document.profile_id != profile.profile_id:
            raise AppError('PROFILE_NOT_SAVED')
        return row

    def replay(self, db, owner_id, key, fingerprint, intent_hash):
        db.execute(delete(ApplicationWriteReceipt).where(ApplicationWriteReceipt.owner_id == owner_id, ApplicationWriteReceipt.expires_at <= utc_now()))
        receipt = db.get(ApplicationWriteReceipt, (owner_id, key))
        if receipt is None:
            if intent_hash is not None and db.scalar(select(ApplicationWriteReceipt.key_id).where(
                ApplicationWriteReceipt.owner_id == owner_id, ApplicationWriteReceipt.intent_hash == intent_hash)) is not None:
                raise AppError('REQUEST_ALREADY_COMPLETED')
            return None
        if receipt.input_hash != fingerprint:
            raise AppError('IDEMPOTENCY_KEY_REUSED')
        row = db.scalar(select(ApplicationDraft).where(ApplicationDraft.owner_id == owner_id,
            ApplicationDraft.document_id == receipt.document_id, ApplicationDraft.version == receipt.version))
        if row is None:
            raise AppError('NOT_FOUND')
        return DraftSaveResult(document_id=row.document_id, version=row.version, saved_at=row.saved_at, profile_version=row.profile_version)

    def write(self, db, account, approved, profile, previous, key, fingerprint, intent_hash):
        draft = approved.draft
        if draft is None or draft.approved_at is None or draft.review_reasons:
            raise AppError('DRAFT_NOT_APPROVED')
        now = utc_now()
        if draft.approved_at > now:
            raise AppError('SERVICE_UNAVAILABLE')
        document_id = previous.document_id if previous else uuid4()
        version = previous.version + 1 if previous else 1
        if version >= 2**31:
            raise AppError('SERVICE_UNAVAILABLE')
        if previous is None:
            db.add(ApplicationDocument(id=document_id, owner_id=account.id, profile_id=profile.profile_id));db.flush()
        content = SavedDraftBody(self_introduction=draft.self_introduction, motivation=draft.motivation)
        try:
            self.profiles.require_cipher()
            envelope = self.profiles.cipher.encrypt(content.model_dump_json().encode('utf-8'), ContentTarget(account.id, 'application', document_id, version, 1))
        except (EncryptionUnavailable, ProtectedContentError):
            raise AppError('SERVICE_UNAVAILABLE') from None
        row = ApplicationDraft(document_id=document_id, version=version, owner_id=account.id, profile_id=profile.profile_id,
            profile_version=profile.version, opportunity_id=draft.opportunity.id, opportunity_version=draft.opportunity.version,
            approved_at=draft.approved_at, saved_at=now, ciphertext=envelope.ciphertext, nonce=envelope.nonce,
            key_id=envelope.key_id, algorithm=envelope.algorithm, schema_version=envelope.schema_version)
        db.add(row)
        db.add(ApplicationWriteReceipt(owner_id=account.id, key_id=key, input_hash=fingerprint, intent_hash=intent_hash,
            document_id=document_id, version=version, profile_id=profile.profile_id, profile_version=profile.version,
            saved_at=now, recorded_at=now, expires_at=now + timedelta(hours=24)))
        db.flush()
        return DraftSaveResult(document_id=document_id, version=version, saved_at=now, profile_version=profile.version)

    def view(self, db, row, *, detail):
        original = db.get(V, (row.opportunity_id, row.opportunity_version))
        if original is None:
            raise AppError('SERVICE_UNAVAILABLE')
        publication = db.get(P, row.opportunity_id)
        current = db.get(V, (row.opportunity_id, publication.version)) if publication is not None else None
        reasons = []
        profile = self.profiles.current(db, row.owner_id)
        if profile is None or profile.profile_id != row.profile_id or profile.version != row.profile_version:
            reasons.append('profile_changed')
        if current is None or publication.review_status != 'approved' or current.review_status != 'approved':
            reasons.append('opportunity_closed')
        else:
            if current.version != row.opportunity_version or self._pending(db, current):
                reasons.append('opportunity_changed')
            if assess_lifecycle(self._snapshot(current), source_checked_at=current.source_checked_at, now=utc_now()).recruitment_status == 'closed':
                reasons.append('opportunity_closed')
        values = dict(document_id=row.document_id, version=row.version, opportunity={'id': row.opportunity_id, 'version': row.opportunity_version},
            opportunity_title=original.title, organization_name=original.organization_name, saved_at=row.saved_at, review_reasons=reasons)
        try:
            if not detail:
                return SavedDraftSummary(**values)
            self.profiles.require_cipher()
            envelope = EncryptedEnvelope(row.ciphertext, row.nonce, row.key_id, row.algorithm, row.schema_version)
            raw = self.profiles.cipher.decrypt(envelope, ContentTarget(row.owner_id, 'application', row.document_id, row.version, row.schema_version))
            content = SavedDraftBody.model_validate_json(raw)
            return SavedDraft(**values, profile_version=row.profile_version, approved_at=row.approved_at, **content.model_dump())
        except (ValidationError, EncryptionUnavailable, ProtectedContentError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    def get(self, db, owner_id, document_id):
        row = self.current(db, owner_id, document_id)
        if row is None:
            raise AppError('NOT_FOUND')
        return self.view(db, row, detail=True)

    def edit_reference(self, db, owner_id, reference):
        row = db.scalar(select(ApplicationDraft).where(ApplicationDraft.owner_id == owner_id,
            ApplicationDraft.document_id == reference.document_id, ApplicationDraft.version == reference.version))
        if row is None:
            raise AppError('NOT_FOUND')
        profile = db.scalar(select(ProfileVersion).where(ProfileVersion.owner_id == owner_id,
            ProfileVersion.profile_id == row.profile_id, ProfileVersion.version == row.profile_version))
        if profile is None:
            raise AppError('NOT_FOUND')
        try:
            self.profiles.require_cipher()
            envelope = EncryptedEnvelope(row.ciphertext, row.nonce, row.key_id, row.algorithm, row.schema_version)
            raw = self.profiles.cipher.decrypt(envelope, ContentTarget(owner_id, 'application', row.document_id, row.version, row.schema_version))
            content = SavedDraftBody.model_validate_json(raw)
            return StoredDraftEditSource(row.document_id, row.version,
                SavedProfileRef(profile_id=row.profile_id, version=row.profile_version),
                OpportunityRef(id=row.opportunity_id, version=row.opportunity_version), self.profiles.content(profile), content)
        except (ValidationError, EncryptionUnavailable, ProtectedContentError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    def listing(self, db, owner_id, page, page_size):
        latest = select(ApplicationDraft.document_id, func.max(ApplicationDraft.version).label('version')).where(
            ApplicationDraft.owner_id == owner_id).group_by(ApplicationDraft.document_id).subquery()
        statement = select(ApplicationDraft).join(latest, (ApplicationDraft.document_id == latest.c.document_id) &
            (ApplicationDraft.version == latest.c.version)).where(ApplicationDraft.owner_id == owner_id)
        total = db.scalar(select(func.count()).select_from(latest))
        rows = [] if (page - 1) * page_size >= total else db.scalars(statement.order_by(ApplicationDraft.saved_at.desc(),
            ApplicationDraft.document_id).limit(page_size).offset((page - 1) * page_size)).all()
        return SavedDraftList(items=[self.view(db, row, detail=False) for row in rows], page=page, page_size=page_size, total=total)
