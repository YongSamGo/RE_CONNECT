"""승인·근거 소유권·현재 공고 뒤에만 암호화 저장하고 일회 대기를 소비한다."""

from uuid import UUID
from dataclasses import dataclass, field

from app.adapters.database import run_query
from app.contracts.journey import ProfileRef
from app.contracts.journey import SavedProfileRef
from app.contracts.profile import ProfileContent
from app.contracts.preparation import OpportunityRef
from app.contracts.saved_drafts import SavedDraftBody
from app.core.business_errors import AppError
from app.modules.requests.service import input_fingerprint
from app.modules.save_intents.service import ApprovedTransfer


@dataclass(frozen=True)
class StoredDraftEditSource:
    document_id: UUID
    version: int
    profile_reference: SavedProfileRef
    opportunity: OpportunityRef
    profile: ProfileContent = field(repr=False)
    content: SavedDraftBody = field(repr=False)


class SavedDraftService:
    def __init__(self, repository, members, consents, intents, journeys, drafts):
        self.repository, self.members, self.consents = repository, members, consents
        self.intents, self.journeys, self.drafts = intents, journeys, drafts

    async def _read(self, session, method, *args):
        account = await self.members.require(session)
        async with self.intents.policy.authorize(account.id, None, None, check_base=False) as db:
            result = await run_query(method, db, account.id, *args)
            await self.members.require(session)
            return result

    async def get(self, session, document_id):
        return await self._read(session, self.repository.get, document_id)

    async def listing(self, session, page, page_size):
        return await self._read(session, self.repository.listing, page, page_size)

    async def edit_source(self, session, reference, *, create=None):
        account = await self.members.require(session)
        notice = self.consents.versions['ai_processing']
        if notice is None:
            raise AppError('CONSENT_REQUIRED')
        async with self.intents.policy.authorize(account.id, notice, None, check_base=False, purpose='ai_processing') as db:
            result = await run_query(self.repository.edit_reference, db, account.id, reference)
            await self.members.require(session)
            if create is not None:
                result = await create(result)
                await self.members.require(session)
            return result

    async def source(self, session, account, source):
        if source.type == 'save_intent':
            approved = await self.intents.take_approved(session, account, source.save_intent_id, consume=False)
        else:
            draft = await self.drafts.get(session, source.journey_id, source.draft_id)
            if draft.revision != source.revision:
                raise AppError('VERSION_CONFLICT')
            profile = await self.journeys.resolve_profile(session,
                ProfileRef(kind='journey', id=source.journey_id, version=draft.profile_version), require_current=True)
            approved = ApprovedTransfer(profile.content, profile.confirmed_at, draft)
        if approved.draft is None or approved.draft.approved_at is None or approved.draft.review_reasons:
            raise AppError('DRAFT_NOT_APPROVED')
        return approved

    async def save(self, session, key, body):
        account = await self.members.require(session)
        self.repository.profiles.require_cipher()
        notice = self.consents.versions['storage']
        if notice is None:
            raise AppError('CONSENT_REQUIRED')
        try:
            key_id = UUID(key)
            if str(key_id) != key.lower():raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AppError('VALIDATION_FAILED') from None
        fingerprint = input_fingerprint(body.model_dump(mode='json'))
        intent_hash = input_fingerprint({'save_intent_id': str(body.source.save_intent_id)}) if body.source.type == 'save_intent' else None
        async with self.intents.policy.authorize(account.id, notice, None, check_base=False) as db:
            replay = await run_query(self.repository.replay, db, account.id, key_id, fingerprint, intent_hash)
            if replay is not None:
                await self.members.require(session)
                return replay
            approved = await self.source(session, account, body.source)
            profile = await run_query(self.repository.profile, db, account.id, approved)
            previous = await run_query(self.repository.document, db, account.id, body, profile)
            await run_query(self.repository.opportunity, db, approved.draft.opportunity)
            if body.source.type == 'save_intent':
                consumed = await self.intents.take_approved(session, account, body.source.save_intent_id)
                if consumed != approved:raise AppError('VERSION_CONFLICT')
            await self.members.require(session)
            result = await run_query(self.repository.write, db, account, approved, profile, previous, key_id, fingerprint, intent_hash)
            if body.source.type == 'journey' and await self.source(session, account, body.source) != approved:
                raise AppError('VERSION_CONFLICT')
            await run_query(self.repository.opportunity, db, approved.draft.opportunity)
            await self.members.require(session)
            return result
