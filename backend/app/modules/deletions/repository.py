"""본문 없는 요청 기록·회원 세대 차단·삭제의 SQL 경계."""

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.database import run_query
from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.modules.deletions.models import DeletedCounts, DeletionEvent
from app.persistence import ApplicationDocument, ApplicationDraft, ApplicationWriteReceipt, Consent, DeletionRecord, ProfileDocument, ProfileVersion, ProfileWriteReceipt, User


class SqlDeletionRepository:
    def __init__(self, transaction):
        self.transaction = transaction

    @staticmethod
    def event(row):
        return DeletionEvent.model_validate({name: getattr(row, name) for name in DeletionEvent.model_fields if name != 'schema_version'})

    def prepare(self, db, account, action, document_id):
        owner = db.get(User, account.id)
        if owner is None or owner.session_generation != account.generation or owner.session_generation >= 2147483646:
            raise AppError('SESSION_EXPIRED')
        target, scope = owner.id, 'account'
        if action in {'profile_delete', 'storage_withdraw'}:
            profile = db.scalar(select(ProfileDocument).where(ProfileDocument.owner_id == owner.id))
            target, scope = profile.id if profile else owner.id, 'profile'
        if action == 'application_delete':
            application = db.scalar(select(ApplicationDocument).where(ApplicationDocument.owner_id == owner.id, ApplicationDocument.id == document_id))
            if application is None: raise AppError('NOT_FOUND')
            target, scope = application.id, 'application'
        now = utc_now(); owner.session_generation += 1
        event = DeletionEvent(id=uuid4(), owner_id=owner.id, scope=scope, target_id=target, action=action,
            generation=owner.session_generation, deleted_at=now, expires_at=now + timedelta(days=30))
        db.add(DeletionRecord(**event.model_dump(exclude={'schema_version'}), status='pending')); db.flush()
        return event

    @staticmethod
    def has_consent(db, owner_id, action):
        purpose = 'ai_processing' if action == 'ai_withdraw' else 'storage'
        row = db.scalar(select(Consent).where(Consent.owner_id == owner_id, Consent.purpose == purpose)
            .order_by(Consent.accepted_at.desc(), Consent.id.desc()).limit(1))
        return row is not None and row.withdrawn_at is None

    @asynccontextmanager
    async def locked(self, owner_id):
        def opened():
            manager = self.transaction(); db = manager.__enter__()
            try:
                if db.bind.dialect.name == 'postgresql':
                    db.execute(text("SET LOCAL statement_timeout = '5s'")); db.execute(text("SET LOCAL lock_timeout = '1s'"))
                db.scalar(select(User).where(User.id == owner_id).with_for_update())
            except BaseException as error:
                manager.__exit__(type(error), error, error.__traceback__); raise
            return manager, db
        task = asyncio.create_task(asyncio.to_thread(opened))
        try:
            manager, db = await asyncio.shield(task)
        except asyncio.CancelledError:
            try: manager, db = await task
            except BaseException: pass
            else: await run_query(manager.__exit__, asyncio.CancelledError, asyncio.CancelledError(), None)
            raise
        except SQLAlchemyError:
            raise AppError('SERVICE_UNAVAILABLE') from None
        try:
            yield db
        except BaseException as error:
            await run_query(manager.__exit__, type(error), error, error.__traceback__)
            if isinstance(error, SQLAlchemyError): raise AppError('SERVICE_UNAVAILABLE') from None
            raise
        else:
            try: await run_query(manager.__exit__, None, None, None)
            except SQLAlchemyError: raise AppError('SERVICE_UNAVAILABLE') from None

    def load(self, db, event):
        row = db.scalar(select(DeletionRecord).where(DeletionRecord.id == event.id).with_for_update())
        if row is None or self.event(row) != event: raise AppError('SERVICE_UNAVAILABLE')
        return row.status

    def remove(self, db, event, journeys):
        counts = {'journeys': journeys, 'profile_versions': 0, 'documents': 0}
        if event.action in {'profile_delete', 'storage_withdraw', 'account_delete'}:
            condition = [ProfileDocument.owner_id == event.owner_id]
            if event.action != 'account_delete': condition.append(ProfileDocument.id == event.target_id)
            profiles = select(ProfileDocument.id).where(*condition)
            counts['profile_versions'] = db.scalar(select(func.count()).select_from(ProfileVersion).where(ProfileVersion.owner_id == event.owner_id, ProfileVersion.profile_id.in_(profiles)))
            counts['documents'] = db.scalar(select(func.count()).select_from(ApplicationDocument).where(ApplicationDocument.owner_id == event.owner_id, ApplicationDocument.profile_id.in_(profiles)))
            db.execute(delete(ApplicationDraft).where(ApplicationDraft.owner_id == event.owner_id, ApplicationDraft.profile_id.in_(profiles)))
            db.execute(delete(ApplicationDocument).where(ApplicationDocument.owner_id == event.owner_id, ApplicationDocument.profile_id.in_(profiles)))
            db.execute(delete(ProfileVersion).where(ProfileVersion.owner_id == event.owner_id, ProfileVersion.profile_id.in_(profiles)))
            db.execute(delete(ProfileDocument).where(*condition))
        if event.action == 'application_delete':
            db.execute(delete(ApplicationDraft).where(ApplicationDraft.owner_id == event.owner_id, ApplicationDraft.document_id == event.target_id))
            result = db.execute(delete(ApplicationDocument).where(ApplicationDocument.owner_id == event.owner_id, ApplicationDocument.id == event.target_id))
            counts['documents'] = result.rowcount
        if event.action in {'ai_withdraw', 'storage_withdraw'}:
            purpose = 'ai_processing' if event.action == 'ai_withdraw' else 'storage'
            db.execute(update(Consent).where(Consent.owner_id == event.owner_id, Consent.purpose == purpose,
                Consent.accepted_at <= event.deleted_at, Consent.withdrawn_at.is_(None)).values(withdrawn_at=event.deleted_at))
        if event.action == 'account_delete':
            for model in (ApplicationWriteReceipt, ProfileWriteReceipt, Consent):
                db.execute(delete(model).where(model.owner_id == event.owner_id))
            db.execute(delete(User).where(User.id == event.owner_id))
        db.execute(update(DeletionRecord).where(DeletionRecord.id == event.id).values(status='completed'))
        db.flush()
        return DeletedCounts(**counts)

    def failed(self, event):
        try:
            with self.transaction() as db:
                db.execute(update(DeletionRecord).where(DeletionRecord.id == event.id, DeletionRecord.status != 'completed').values(status='failed'))
        except SQLAlchemyError:
            pass  # 원래 pending도 재시도 대상이다. 오류 본문은 보관하지 않는다.

    def pending(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100: raise AppError('VALIDATION_FAILED')
        try:
            with self.transaction() as db:
                rows = db.scalars(select(DeletionRecord).where(DeletionRecord.status.in_(['pending', 'failed']))
                    .order_by(DeletionRecord.deleted_at, DeletionRecord.id).limit(limit)).all()
                return [self.event(row) for row in rows]
        except (SQLAlchemyError, ValueError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    def restore(self, db, event):
        row = db.get(DeletionRecord, event.id)
        if row is not None:
            if self.event(row) != event: raise AppError('SERVICE_UNAVAILABLE')
            row.status = 'pending'
        else:
            db.add(DeletionRecord(**event.model_dump(exclude={'schema_version'}), status='pending'))
        owner = db.get(User, event.owner_id)
        if owner is not None: owner.session_generation = max(owner.session_generation, event.generation)
        db.flush()

    def prune(self, now):
        try:
            with self.transaction() as db:
                return db.execute(delete(DeletionRecord).where(DeletionRecord.expires_at <= now,
                    DeletionRecord.status == 'completed')).rowcount
        except SQLAlchemyError:
            raise AppError('SERVICE_UNAVAILABLE') from None


class UnavailableDeletionRepository:
    def pending(self, *args):
        raise AppError('SERVICE_UNAVAILABLE')

    prepare = failed = restore = prune = has_consent = pending

    @asynccontextmanager
    async def locked(self, *args):
        raise AppError('SERVICE_UNAVAILABLE')
        yield
