"""확정 사실 선택으로 만드는 미승인 지원서와 AI 없는 빈 초안."""

import asyncio
from uuid import UUID

from pydantic import ValidationError

from app.adapters.llm import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError
from app.contracts.drafts import DraftCreate, DraftUpdate, JourneyDraft
from app.contracts.journey import ProfileRef
from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.modules.generation.models import ApplicationContext, ConfirmedProfileSnapshot
from app.modules.generation.service import GenerationInputError, GroundedGenerationService
from app.modules.opportunities.lifecycle import assess_lifecycle
from app.modules.requests.service import input_fingerprint

DRAFT_TIMEOUT_SECONDS = 60


class DraftService:
    def __init__(self, store, journeys, opportunities, llm):
        self.store, self.journeys, self.opportunities, self.llm = store, journeys, opportunities, llm

    async def _display(self, session, journey_id: UUID, draft: JourneyDraft) -> JourneyDraft:
        dependency = await self.journeys.profile_dependency(session, ProfileRef(kind='journey', id=journey_id, version=draft.profile_version))
        reasons, warnings = list(dependency.review_reasons), []
        if dependency.based_on_previous_confirmed:
            warnings.append('프로필을 수정 중입니다. 이 지원서는 원래 확정 프로필 기준이며 본문은 자동으로 바뀌지 않습니다.')
        try:
            opportunity = await asyncio.to_thread(self.opportunities.get, draft.opportunity.id)
        except AppError as error:
            if error.code != 'NOT_FOUND':
                raise
            reasons.append('opportunity_closed')
        else:
            if opportunity.recruitment_status == 'closed':
                reasons.append('opportunity_closed')
            if opportunity.version != draft.opportunity.version or opportunity.change_pending:
                reasons.append('opportunity_changed')
            if not assess_lifecycle(opportunity, source_checked_at=opportunity.source_checked_at, now=utc_now()).recommendation_allowed:
                warnings.append('공고의 현재 모집 상태·마감·확인 시각을 다시 확인해 주세요. 새 생성·승인이 제한될 수 있습니다.')
        if reasons:
            warnings.append('근거가 변경되었습니다. 기존 본문은 보존되며 새 근거로 만들고 확인·승인해야 합니다.')
        return draft.model_copy(update={'review_reasons': list(dict.fromkeys(reasons)),
            'warnings': list(dict.fromkeys([*warnings, *draft.warnings]))[:10]})

    async def get(self, session, journey_id: UUID, draft_id: UUID) -> JourneyDraft:
        original = await self.store.read(session, journey_id, draft_id)
        displayed = await self._display(session, journey_id, original)
        # SQL 조회 도중 종료/편집된 지원서를 이전 본문으로 돌려주지 않는다.
        if await self.store.read(session, journey_id, draft_id) != original:
            raise AppError('VERSION_CONFLICT')
        dependency = await self.journeys.profile_dependency(session, ProfileRef(kind='journey', id=journey_id, version=original.profile_version))
        if bool(dependency.review_reasons) != ('profile_changed' in displayed.review_reasons):
            raise AppError('VERSION_CONFLICT')
        return displayed

    async def update(self, session, journey_id: UUID, draft_id: UUID, body: DraftUpdate) -> JourneyDraft:
        previous = await self.store.read(session, journey_id, draft_id)
        if previous.revision != body.base_revision:
            raise AppError('VERSION_CONFLICT')
        updated = JourneyDraft.model_validate({**previous.model_dump(), 'revision': previous.revision + 1,
            'self_introduction': body.self_introduction, 'motivation': body.motivation, 'approved_at': None})
        displayed = await self._display(session, journey_id, updated)
        await self.store.mutate(session, journey_id, previous, updated)
        return displayed

    async def approve(self, session, journey_id: UUID, draft_id: UUID, base_revision: int) -> JourneyDraft:
        previous = await self.store.read(session, journey_id, draft_id)
        if previous.revision != base_revision:
            raise AppError('VERSION_CONFLICT')
        reference = ProfileRef(kind='journey', id=journey_id, version=previous.profile_version)
        await self.journeys.resolve_profile(session, reference, require_current=True)
        view = await self.journeys.profile(session, journey_id)
        await self._opportunity(previous.opportunity)
        updated = JourneyDraft.model_validate({**previous.model_dump(), 'revision': previous.revision + 1,
            'approved_at': utc_now(), 'review_reasons': []})
        return await self.store.mutate(session, journey_id, previous, updated, journey_revision=view.revision)

    async def _opportunity(self, reference):
        try:
            opportunity = await asyncio.to_thread(self.opportunities.get, reference.id)
        except AppError as error:
            if error.code == 'NOT_FOUND':
                raise AppError('OPPORTUNITY_NOT_AVAILABLE') from None
            raise
        if opportunity.version != reference.version:
            raise AppError('VERSION_CONFLICT')
        if opportunity.change_pending or not assess_lifecycle(opportunity, source_checked_at=opportunity.source_checked_at, now=utc_now()).recommendation_allowed:
            raise AppError('OPPORTUNITY_NOT_AVAILABLE')
        return opportunity

    async def create(self, session, identity, journey_id: UUID, key: str, body: DraftCreate) -> JourneyDraft:
        if identity.subject_id != session.subject_id or identity.account_id != session.user_id:
            raise AppError('NOT_FOUND')
        if body.mode == 'from_saved':
            # 실제 회원 인증/암호화 저장본 소유권 연결 전에는 문서 ID를 신뢰하지 않는다.
            raise AppError('UNAUTHENTICATED')
        try:
            key_id = UUID(key)
            if str(key_id) != key.lower():
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AppError('VALIDATION_FAILED') from None
        reference = ProfileRef(kind='journey', id=journey_id, version=body.profile_version)
        snapshot = await self.journeys.resolve_profile(session, reference, require_current=True)
        view = await self.journeys.profile(session, journey_id)
        opportunity = await self._opportunity(body.opportunity)
        notice = (await self.journeys.load(session, journey_id)).guard.ai_notice_version if body.mode == 'generate' else ''
        permit = await self.store.reserve(session, journey_id, key_id, input_fingerprint(body.model_dump(mode='json')),
            view.revision, body.profile_version, notice)
        if isinstance(permit, JourneyDraft):
            return permit
        try:
            paragraphs, warnings = [], []
            if body.mode == 'generate':
                async with asyncio.timeout(DRAFT_TIMEOUT_SECONDS):
                    preview = await GroundedGenerationService(self.llm.for_identity(identity)).application_preview(
                        snapshot=ConfirmedProfileSnapshot(profile_id=journey_id, version=body.profile_version, content=snapshot.content),
                        context=ApplicationContext(opportunity=body.opportunity, title=opportunity.title, description=opportunity.description_text))
                for paragraph in preview.paragraphs:
                    if len('\n'.join([*paragraphs, paragraph])) <= 2000:
                        paragraphs.append(paragraph)
                    else:
                        warnings = ['일부 확정 사실은 본문 길이 제한으로 포함하지 않았습니다.']
                warnings.append('지원동기는 추정하지 않았습니다. 공고를 확인하고 직접 작성해 주세요.')
            draft = JourneyDraft(draft_id=permit.draft_id, revision=1, mode=body.mode, profile_version=body.profile_version,
                opportunity=body.opportunity, self_introduction='\n'.join(paragraphs), motivation='', approved_at=None,
                review_reasons=[], warnings=warnings)
            await self.journeys.resolve_profile(session, reference, require_current=True)
            latest = await self._opportunity(body.opportunity)
            if latest != opportunity:
                raise AppError('VERSION_CONFLICT')
            return await self.store.complete(session, journey_id, permit, draft)
        except BaseException as error:
            try:
                await asyncio.shield(self.store.cancel(session, journey_id, permit))
            except AppError:
                pass
            if isinstance(error, (TimeoutError, LLMTimeoutError)):
                raise AppError('AI_TIMEOUT') from None
            if isinstance(error, (LLMUnavailableError, LLMInvalidOutputError)):
                raise AppError('MODEL_UNAVAILABLE') from None
            if isinstance(error, (GenerationInputError, ValidationError)):
                raise AppError('VALIDATION_FAILED') from None
            raise
