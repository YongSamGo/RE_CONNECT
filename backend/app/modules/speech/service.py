"""서버가 소유권/표시 버전을 확인한 한 조각만 내부 고정 화자로 읽는다."""

import asyncio
from dataclasses import dataclass, field

from app.adapters.speech import SpeechInvalidInputError, SpeechInvalidOutputError, SpeechTimeoutError, SpeechUnavailableError
from app.contracts.speech import SpeechRequest
from app.core.business_errors import AppError
from app.modules.consents.service import ConsentActor
from app.modules.requests.service import CompletionGuard, RequestScope, ResourceReadCheck, SessionCompletionGuard, Replay


@dataclass(frozen=True)
class ReadSource:
    text: str = field(repr=False)
    guard: CompletionGuard | None = None
    journey_id: object = None
    revision: int | None = None
    check: ResourceReadCheck | None = None


class SpeechService:
    def __init__(self, journeys, drafts, opportunities, consents, requests, speech):
        self.journeys, self.drafts, self.opportunities = journeys, drafts, opportunities
        self.consents, self.requests, self.speech = consents, requests, speech

    async def _source(self, session, target) -> ReadSource:
        if target.kind == 'saved_draft':
            raise AppError('UNAUTHENTICATED')
        if target.kind == 'opportunity':
            opportunity = await asyncio.to_thread(self.opportunities.get, target.opportunity_id)
            if opportunity.version != target.version:
                raise AppError('VERSION_CONFLICT')
            content = getattr(opportunity, target.field)
            if not isinstance(content, str) or not content.strip():
                raise AppError('VALIDATION_FAILED')
            return ReadSource(content)
        record = await self.journeys.load(session, target.journey_id)
        check = None
        if target.kind == 'journey_message':
            content = (await self.journeys.question(session, target.journey_id, target.message_id)).text
        else:
            draft = await self.drafts.read_source(session, target.journey_id, target.draft_id)
            if draft.revision != target.revision:
                raise AppError('VERSION_CONFLICT')
            content = getattr(draft, target.field)
            check = ResourceReadCheck(f'draft:{draft.draft_id}', draft.model_dump_json())
        if not isinstance(content, str) or not content.strip():
            raise AppError('VALIDATION_FAILED')
        return ReadSource(content, record.guard, target.journey_id, record.view.revision, check)

    async def read(self, session, identity, key: str, body: SpeechRequest) -> tuple[bytes, int]:
        if identity.subject_id != session.subject_id or identity.account_id != session.user_id:
            raise AppError('NOT_FOUND')
        consent = await self.consents.require(ConsentActor(session.subject_id, member_id=session.user_id,
            session_digest=session.digest, member_generation=session.user_generation), 'ai_processing')
        source = await self._source(session, body.target)
        parts = [source.text[index:index + 2000] for index in range(0, len(source.text), 2000) if source.text[index:index + 2000].strip()]
        if body.segment >= len(parts):
            raise AppError('VALIDATION_FAILED')
        guard = SessionCompletionGuard(session.digest, consent.notice_version, round(consent.granted_at.timestamp() * 1000))
        permit = await self.requests.begin(RequestScope(session.subject_id, 'speech', source.journey_id), key,
            body.model_dump(mode='json'), base_revision=source.revision)
        if isinstance(permit, Replay):
            raise AppError('REQUEST_ALREADY_COMPLETED')
        try:
            audio = await self.speech.synthesize(parts[body.segment], identity=identity)
            if await self._source(session, body.target) != source:
                raise AppError('VERSION_CONFLICT')
            await self.requests.complete_readonly(permit, session=guard, resource=source.guard, source=source.check)
            return audio, len(parts)
        except BaseException as error:
            try:
                await asyncio.shield(self.requests.cancel(permit))
            except AppError:
                pass
            if isinstance(error, SpeechTimeoutError):
                raise AppError('AI_TIMEOUT') from None
            if isinstance(error, (SpeechUnavailableError, SpeechInvalidOutputError)):
                raise AppError('MODEL_UNAVAILABLE') from None
            if isinstance(error, SpeechInvalidInputError):
                raise AppError('VALIDATION_FAILED') from None
            raise
