"""확인 텍스트의 근거 제한 추출. 완료 전까지 기존 초안/확정본을 변경하지 않는다."""

import asyncio
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.adapters.llm import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError
from app.contracts.journey import ConversationTurn, Message, MessageCommit, MessageCreate, MessageResult, ProfileDraftView, ProfileEvidence
from app.contracts.profile import Experience, ProfileContent
from app.contracts.roles import normalize_tag
from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.modules.admission.llm import ControlledLLMAdapter
from app.modules.admission.service import InferenceIdentity
from app.modules.generation import questions
from app.modules.generation.privacy import safe_text
from app.modules.generation.service import GenerationInputError, GroundedGenerationService
from app.modules.journeys.service import JourneyService
from app.modules.requests.service import Replay, RequestScope, RequestService, ResultReference
from app.modules.sessions.service import Session

MESSAGE_TIMEOUT_SECONDS = 60


def _enrich(experiences: list[Experience], evidence: list[ProfileEvidence], proposal, message_id: UUID) -> None:
    """기존 경험에 이번 턴의 세부 내용을 덧붙인다. 설명은 바꾸지 않고, 태그는 더하기만 하며 기간은 비어 있을 때만 채운다.

    사용자가 고친 값을 모델이 지우거나 바꾸지 않게 하려는 규칙이다. 덧붙인 근거로 이번 메시지를 기록한다.
    """
    index = next((i for i, item in enumerate(experiences) if item.id == proposal.id), None)
    if index is None:
        return
    current = experiences[index]
    known = {normalize_tag(tag) for tag in current.skill_tags}
    added = [tag for tag in proposal.skill_tags if normalize_tag(tag) not in known][:max(0, 20 - len(current.skill_tags))]
    duration = current.duration_note or proposal.duration_note
    if not added and duration == current.duration_note:
        return
    experiences[index] = current.model_copy(update={'skill_tags': [*current.skill_tags, *added], 'duration_note': duration})
    path = f'experiences[{index}]'
    for position, item in enumerate(evidence):
        if item.path == path:
            if message_id not in item.message_ids:
                evidence[position] = item.model_copy(update={'message_ids': [*item.message_ids, message_id]})
            return
    evidence.append(ProfileEvidence(path=path, message_ids=[message_id]))


class JourneyMessageService:
    def __init__(self, journeys: JourneyService, requests: RequestService, llm: ControlledLLMAdapter, transcriptions=None,
                 catalog=None):
        self.journeys, self.requests, self.llm = journeys, requests, llm
        self.transcriptions = transcriptions
        # 역할 사전(RoleCatalog). 표준 기술 태그 선택지로만 쓴다. 없거나 읽지 못하면 원문 기술 구절만 남는다.
        self.catalog = catalog

    def _standard_tags(self) -> dict[str, list[str]]:
        """표준 기술 태그 → 검토된 별칭. 생성 서비스가 원문 근거와 대조할 때 쓴다."""
        try:
            roles = self.catalog.list() if self.catalog is not None else []
        except AppError:
            return {}
        tags: dict[str, list[str]] = {}
        for role in roles:
            for tag in role.skill_tags:
                tags.setdefault(tag, [])
            for alias in role.aliases:
                tags.setdefault(alias.skill_tag, []).append(alias.alias)
        return tags

    async def send(self, session: Session, identity: InferenceIdentity, journey_id: UUID, key: str, body: MessageCreate) -> MessageResult:
        if identity.subject_id != session.subject_id or identity.account_id != session.user_id:
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
            loop = asyncio.get_running_loop()
            deadline = loop.time() + MESSAGE_TIMEOUT_SECONDS
            standard_tags = await asyncio.to_thread(self._standard_tags)
            async with asyncio.timeout_at(deadline):
                preview = await generation.extract_experiences(user_texts=[turn.text for turn in turns],
                    existing_experiences=current.draft.experiences, standard_tags=standard_tags)
                experiences = list(current.draft.experiences)
                evidence = list(current.evidence)
                for proposal, source in zip(preview.experiences, preview.source_turns, strict=True):
                    # 이전 턴만으로 삭제한 경험을 되살리지 않는다. 이번 확인 텍스트가 근거인 것만 반영한다.
                    # 문구는 다듬어지고 태그는 표준 태그일 수 있어, 생성 서비스가 원문과 대조한 근거 턴 번호로 확인한다.
                    if source != len(turns) - 1:
                        continue
                    if proposal.id is not None:
                        _enrich(experiences, evidence, proposal, turns[-1].message_id)
                        continue
                    if any(e.description == proposal.description for e in experiences):
                        continue
                    evidence.append(ProfileEvidence(path=f'experiences[{len(experiences)}]', message_ids=[turns[-1].message_id]))
                    experiences.append(Experience(id=uuid4(), description=proposal.description,
                        duration_note=proposal.duration_note, skill_tags=proposal.skill_tags))
                # 지역·활동 유형 질문에 대한 답이면 정해진 목록과 맞춰 초안에 넣는다(모델 없음). 이미 고른 값은 덮지 않는다.
                updates: dict = {'experiences': experiences}
                answered = turns[-2].next_question if len(turns) > 1 else questions.FIRST_ID
                if answered == 'cond.region' and not current.draft.preferred_regions:
                    updates['preferred_regions'] = questions.read_regions(body.text)
                if answered == 'cond.type' and not current.draft.activity_types:
                    updates['activity_types'] = questions.read_activity_types(body.text)
                for field in ('preferred_regions', 'activity_types'):
                    if updates.get(field):
                        evidence.append(ProfileEvidence(path=field, message_ids=[turns[-1].message_id]))
                draft = ProfileContent.model_validate({**current.draft.model_dump(), **updates})
                await self.journeys.load(session, journey_id)
                if (await self.journeys.profile(session, journey_id)).revision != body.base_revision:
                    raise AppError('VERSION_CONFLICT')
            # 다음 질문은 서버 규칙으로 고른다(모델 호출 없음). 고른 ID를 이번 답에 남겨 같은 질문을 되풀이하지 않는다.
            asked = [questions.FIRST_ID, *(turn.next_question for turn in turns[:-1] if turn.next_question)]
            question_id = questions.next_question(draft, asked, body.text)
            turns[-1] = turns[-1].model_copy(update={'next_question': question_id})
            question = questions.text_of(question_id) if question_id else None
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
