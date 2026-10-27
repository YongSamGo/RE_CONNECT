"""삭제 요청을 영속화해 처리를 차단하고 외부 이력·Redis·SQL을 순서대로 완료한다."""

import asyncio
from functools import partial

from app.adapters.database import run_query
from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.modules.deletions.models import DeletedCounts
from app.modules.sessions.service import StoreUnavailable


class DeletionService:
    def __init__(self, repository, journal, members, policy, cleanup):
        self.repository, self.journal, self.members = repository, journal, members
        self.policy, self.cleanup = policy, cleanup

    async def request(self, session, action, document_id=None):
        account = await self.members.require(session, reauth=action == 'account_delete')
        async with self.policy.authorize(account.id, None, None, check_base=False) as db:
            if action in {'storage_withdraw', 'ai_withdraw'} and not await run_query(self.repository.has_consent, db, account.id, action):
                await self.members.require(session)
                return None, DeletedCounts(journeys=0, profile_versions=0, documents=0), None
            await run_query(self.journal.check)
            # 미확정 요청을 외부에 남기지 않는다. 먼저 pending/세대만 커밋한다.
            event = await run_query(self.repository.prepare, db, account, action, document_id)
            await self.members.require(session, reauth=action == 'account_delete')
        counts = await self.finish(event)
        # 모든 이전 세션을 폐기했다. 호출자는 새 주체·CSRF로 다시 결합한다.
        issued = await self.members.sessions.issue()
        if action != 'account_delete':
            latest = await run_query(self.members.accounts.get, account.id)
            if latest is not None and latest.generation == event.generation:
                replacement = None
                try:
                    replacement = await self.members._switch(issued.session, account.id, generation=event.generation)
                    await self.members.require(replacement.session)
                    issued = replacement
                except BaseException:
                    if replacement is not None: await self.members.sessions.revoke(replacement.token)
                    await self.members.sessions.revoke(issued.token)
                    raise
        return event, counts, issued

    async def finish(self, event):
        try:
            async with self.repository.locked(event.owner_id) as db:
                status = await run_query(self.repository.load, db, event)
                if status == 'completed': return DeletedCounts(journeys=0, profile_versions=0, documents=0)
                if event.expires_at <= utc_now(): raise AppError('SERVICE_UNAVAILABLE')
                # 외부 이력의 fsync 성공 전에는 실제 자료를 삭제하거나 성공 응답하지 않는다.
                await run_query(self.journal.append, event)
                journeys = await self.cleanup.revoke(event.owner_id)
                return await run_query(self.repository.remove, db, event, journeys)
        except BaseException as error:
            await asyncio.shield(run_query(self.repository.failed, event))
            if isinstance(error, StoreUnavailable): raise AppError('SERVICE_UNAVAILABLE') from None
            raise

    async def retry(self, limit=100):
        events = await run_query(self.repository.pending, limit)
        for event in events: await self.finish(event)
        return len(events)

    async def recover(self, limit=1000):
        # 복원 DB 공개 전에 DB 밖 최신 이력의 같은 대상 UUID에 삭제를 재적용한다.
        events = await run_query(partial(self.journal.events, utc_now(), limit=limit))
        for event in events:
            async with self.repository.locked(event.owner_id) as db:
                await run_query(self.repository.restore, db, event)
            await self.finish(event)
        return len(events)

    async def prune(self):
        now = utc_now()
        await run_query(self.journal.prune, now)
        return await run_query(self.repository.prune, now)
