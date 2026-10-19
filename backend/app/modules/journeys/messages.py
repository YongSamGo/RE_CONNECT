"""확인 텍스트의 근거 제한 추출. 완료 전까지 기존 초안/확정본을 변경하지 않는다."""

import asyncio
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.adapters.llm import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError
from app.contracts.journey import ConversationTurn, Message, MessageCommit, MessageCreate, MessageResult, ProfileDraftView, ProfileEvidence
from app.contracts.profile import Experience, ProfileContent
from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.modules.admission.llm import ControlledLLMAdapter
from app.modules.admission.service import InferenceIdentity
from app.modules.generation.privacy import safe_text
from app.modules.generation.service import GenerationInputError, GroundedGenerationService
from app.modules.journeys.service import JourneyService
from app.modules.requests.service import Replay, RequestScope, RequestService, ResultReference
from app.modules.sessions.service import Session

MESSAGE_TIMEOUT_SECONDS = 60


class JourneyMessageService:
    def __init__(self, journeys: JourneyService, requests: RequestService, llm: ControlledLLMAdapter, transcriptions=None):
        self.journeys, self.requests, self.llm = journeys, requests, llm
        self.transcriptions = transcriptions

    async def send(self, session: Session, identity: InferenceIdentity, journey_id: UUID, key: str, body: MessageCreate) -> MessageResult:
        if identity.subject_id != session.subject_id or identity.account_id is not None:
            raise AppError('NOT_FOUND')
        record = await self.journeys.load(session, journey_id)
        if body.transcription_id is not None:
            if self.transcriptions is None:
                raise AppError('NOT_FOUND')
            # 원문을 자동 추출하지 않는다. 전사 ID 소유권만 확인하고 body.text만 사용한다.
            await self.transcriptions.require(session, journey_id, body.transcription_id)
        if safe_text(body.text) is None:
            raise AppError('VALIDATION_FAILED')
        permit = await self.requests.begin(RequestScope(session.subject_id, 'messages', journey_id), key,
            body.model_dump(mode='json'), base_revision=body.base_revision)
        if isinstance(permit, Replay):
            return await self.journeys.message_result(session, journey_id, record.guard.ai_notice_version, permit.result)
        try:
            current = await self.journeys.profile(session, journey_id)
            if current.revision != body.base_revision:
                raise AppError('VERSION_CONFLICT')
            turns = await self.journeys.conversation(session, journey_id, record.guard.ai_notice_version)
            turns.append(ConversationTurn(message_id=uuid4(), text=body.text))
            if len(turns) > 64 or sum(len(turn.text.encode('utf-8')) for turn in turns) > 12000:
                raise AppError('PAYLOAD_TOO_LARGE')
            generation = GroundedGenerationService(self.llm.for_identity(identity))
            async with asyncio.timeout(MESSAGE_TIMEOUT_SECONDS):
                preview = await generation.extract_experiences(user_texts=[turn.text for turn in turns],
                    existing_experiences=current.draft.experiences)
                experiences = list(current.draft.experiences)
                evidence = list(current.evidence)
                for proposal in preview.experiences:
                    # 이미 사용자가 편집한 경험은 모델이 교체하지 않는다.
                    if proposal.id is not None or any(e.description == proposal.description for e in experiences):
                        continue
                    # 이전 턴만으로 삭제한 경험을 되살리지 않는다. 이번 확인 텍스트의 사실만 추가한다.
                    matching = [turn.message_id for turn in turns[-1:] if proposal.description in turn.text
                        and (proposal.duration_note is None or proposal.duration_note in turn.text)
                        and all(tag in turn.text for tag in proposal.skill_tags)]
                    if not matching:
                        continue
                    evidence.append(ProfileEvidence(path=f'experiences[{len(experiences)}]', message_ids=matching))
                    experiences.append(Experience(id=uuid4(), description=proposal.description,
                        duration_note=proposal.duration_note, skill_tags=proposal.skill_tags))
                draft = ProfileContent.model_validate({**current.draft.model_dump(), 'experiences': experiences})
                await self.journeys.load(session, journey_id)
                if (await self.journeys.profile(session, journey_id)).revision != body.base_revision:
                    raise AppError('VERSION_CONFLICT')
                question = await generation.next_question(missing_fields=draft.missing_for_recommendation())
            revision = body.base_revision + 1
            view = ProfileDraftView(revision=revision, draft=draft, evidence=evidence, confirmed=current.confirmed,
                has_unconfirmed_changes=current.confirmed is not None, missing_for_recommendation=draft.missing_for_recommendation())
            response = MessageResult(revision=revision, user_message_id=turns[-1].message_id,
                assistant_message=Message(message_id=uuid4(), text=question, created_at=utc_now()) if question else None,
                profile=view, notices=[], next_step='continue' if question else 'review_profile')
            commit = MessageCommit(response=response, turns=turns)
            await self.requests.complete(permit, ResultReference('message', response.user_message_id, revision),
                guard=record.guard, message=commit)
            return response
        except BaseException as error:
            # HTTP 취소는 실제 런타임 종료를 뜻하지 않는다. 재시도용 실행권만 폐기한다.
            try:
                await asyncio.shield(self.requests.cancel(permit))
            except AppError:
                pass
            if isinstance(error, (TimeoutError, LLMTimeoutError)):
                raise AppError('AI_TIMEOUT') from None
            if isinstance(error, (LLMUnavailableError, LLMInvalidOutputError)):
                raise AppError('MODEL_UNAVAILABLE') from None
            if isinstance(error, (GenerationInputError, ValidationError)):
                raise AppError('VALIDATION_FAILED') from None
            raise
