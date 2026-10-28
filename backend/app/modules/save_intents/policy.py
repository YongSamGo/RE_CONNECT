"""회원의 현재 상태·저장 동의·교체 기준을 SQL 잠금 안에서 검사한다."""

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import exists, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.business_errors import AppError
from app.persistence import Consent, DeletionRecord, ProfileVersion, User


class SqlSaveIntentPolicy:
    def __init__(self, transaction):
        self.transaction = transaction

    @staticmethod
    def _check(db, user_id, notice=None, base=None, check_base=True, purpose='storage'):
        if purpose not in {'storage', 'ai_processing'}:
            raise AppError('CONSENT_REQUIRED')
        if db.bind.dialect.name == 'postgresql':
            db.execute(text("SET LOCAL statement_timeout = '5s'"))
            db.execute(text("SET LOCAL lock_timeout = '1s'"))
        owner = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if owner is None or owner.status != 'active':
            raise AppError('SESSION_EXPIRED')
        if db.scalar(select(exists().where(DeletionRecord.owner_id == user_id, DeletionRecord.status.in_(['pending', 'failed'])))):
            raise AppError('SESSION_EXPIRED')
        version = db.scalar(select(func.max(ProfileVersion.version)).where(ProfileVersion.owner_id == user_id))
        if notice is not None:
            consent = db.scalar(select(Consent).where(Consent.owner_id == user_id, Consent.purpose == purpose)
                .order_by(Consent.accepted_at.desc(), Consent.id.desc()).limit(1))
            if consent is None or consent.withdrawn_at is not None or consent.notice_version != notice:
                raise AppError('CONSENT_REQUIRED')
            if check_base and version != base:
                raise AppError('VERSION_CONFLICT')
        return version

    def _version(self, user_id):
        with self.transaction() as db:
            return self._check(db, user_id)

    async def current_version(self, user_id):
        try:
            return await asyncio.to_thread(self._version, user_id)
        except SQLAlchemyError:
            raise AppError('SERVICE_UNAVAILABLE') from None

    def _barrier(self, user_id):
        with self.transaction() as db:
            if db.bind.dialect.name == 'postgresql':
                db.execute(text("SET LOCAL statement_timeout = '5s'"))
                db.execute(text("SET LOCAL lock_timeout = '1s'"))
            db.scalar(select(User.id).where(User.id == user_id).with_for_update())

    async def barrier(self, user_id):
        try:
            await asyncio.to_thread(self._barrier, user_id)
        except SQLAlchemyError:
            raise AppError('SERVICE_UNAVAILABLE') from None

    @asynccontextmanager
    async def authorize(self, user_id, notice, base, *, check_base=True, purpose='storage'):
        # 동의 철회·회원 삭제도 동일 User 행을 잠가야 한다. 저장 소비자는 이 db를 재사용한다.
        def opened():
            manager = self.transaction()
            db = manager.__enter__()
            try:
                self._check(db, user_id, notice, base, check_base, purpose)
            except BaseException as error:
                manager.__exit__(type(error), error, error.__traceback__)
                raise
            return manager, db

        task = asyncio.create_task(asyncio.to_thread(opened))
        try:
            manager, db = await asyncio.shield(task)
        except asyncio.CancelledError:
            # worker의 잠금/조회가 끝나기 전에 다른 스레드에서 같은 연결을 닫지 않는다.
            try:
                manager, db = await task
            except BaseException:
                pass
            else:
                await asyncio.shield(asyncio.to_thread(manager.__exit__, asyncio.CancelledError, asyncio.CancelledError(), None))
            raise
        except SQLAlchemyError:
            raise AppError('SERVICE_UNAVAILABLE') from None
        try:
            yield db
        except BaseException as error:
            await asyncio.shield(asyncio.to_thread(manager.__exit__, type(error), error, error.__traceback__))
            if isinstance(error, SQLAlchemyError):
                raise AppError('SERVICE_UNAVAILABLE') from None
            raise
        else:
            try:
                await asyncio.to_thread(manager.__exit__, None, None, None)
            except SQLAlchemyError:
                raise AppError('SERVICE_UNAVAILABLE') from None


class UnavailableSaveIntentPolicy:
    async def current_version(self, *args):
        raise AppError('SERVICE_UNAVAILABLE')

    barrier = current_version

    @asynccontextmanager
    async def authorize(self, *args):
        raise AppError('SERVICE_UNAVAILABLE')
        yield
