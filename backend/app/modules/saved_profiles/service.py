"""현재 회원·저장 동의·명시 교체 기준과 원자 SQL 멱등 기록을 결합한다."""

from uuid import UUID
from app.adapters.database import run_query

from app.contracts.journey import ProfileRef
from app.contracts.saved_profiles import SavedProfileResponse
from app.core.business_errors import AppError
from app.modules.requests.service import input_fingerprint
from app.modules.save_intents.service import ApprovedTransfer


class SavedProfileService:
    def __init__(self, repository, members, consents, intents, journeys):
        self.repository, self.members, self.consents, self.intents, self.journeys = repository, members, consents, intents, journeys

    async def get(self, session):
        account = await self.members.require(session)
        async with self.intents.policy.authorize(account.id, None, None, check_base=False) as db:
            view = await run_query(self.repository.view, db, account.id)
            await self.members.require(session)
            return SavedProfileResponse(saved=view)

    async def save(self, session, key, body):
        account = await self.members.require(session)
        self.repository.require_cipher()
        notice = self.consents.versions['storage']
        if notice is None:
            raise AppError('CONSENT_REQUIRED')
        try:
            key_id = UUID(key)
            if str(key_id) != key.lower():
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AppError('VALIDATION_FAILED') from None
        fingerprint = input_fingerprint(body.model_dump(mode='json'))
        # 같은 키의 완료 응답은 소비된 대기/과거 base를 다시 검사하기 전에 SQL에서 찾는다.
        async with self.intents.policy.authorize(account.id, notice, None, check_base=False) as db:
            replay = await run_query(self.repository.replay, db, account.id, key_id, fingerprint)
            if replay is not None:
                await self.members.require(session)
                return replay
            await run_query(self.repository.check_base, db, account.id, body.base_saved_version)
            if body.source.type == 'save_intent':
                approved = await self.intents.take_approved(session, account, body.source.save_intent_id, allow_draft=False)
            else:
                reference = ProfileRef(kind='journey', id=body.source.journey_id, version=body.source.version)
                source = await self.journeys.resolve_profile(session, reference, require_current=True)
                approved = ApprovedTransfer(source.content, source.confirmed_at, None)
            await self.members.require(session)
            result = await run_query(self.repository.write, db, account, approved, key_id, fingerprint)
            if body.source.type == 'journey':
                latest = await self.journeys.resolve_profile(session, reference, require_current=True)
                if latest != source:
                    raise AppError('VERSION_CONFLICT')
            await self.members.require(session)
            return result
