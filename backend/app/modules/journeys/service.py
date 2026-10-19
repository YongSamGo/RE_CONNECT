"""생성·조회·활동 수명. 모델 호출·자동 승인·저장 프로필 사칭을 허용하지 않는다."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from app.contracts.journey import Journey, JourneyCreate, ProfileDraftView, ProfileUpdate, ProfileRef, ProfileConfirmResult
from app.contracts.profile import ProfileContent
from app.core.business_errors import AppError
from app.modules.admission.service import AdmissionService, InferenceIdentity
from app.modules.consents.service import ConsentActor, ConsentService
from app.modules.requests.service import CompletionGuard, input_fingerprint
from app.modules.sessions.service import Session

FIRST_QUESTION = "지금까지 해 오신 일 가운데 기억에 남는 일을 한 가지 들려주세요."


@dataclass(frozen=True)
class JourneyRecord:
    view: Journey
    guard: CompletionGuard = field(repr=False)


class MissingProfileFields(Exception):
    def __init__(self, fields):
        self.fields = tuple(fields)
        super().__init__("확정에 필요한 항목이 없습니다")


@dataclass(frozen=True)
class ResolvedJourneyProfile:
    reference: ProfileRef
    content: ProfileContent = field(repr=False)
    confirmed_at: datetime


class JourneyStore(Protocol):
    async def create(self, session: Session, key_id: UUID, fingerprint: str, notice_version: str,
                     budget: str, key_id_digest: str) -> JourneyRecord: ...
    async def load(self, session: Session, journey_id: UUID, notice_version: str, *, user_activity: bool) -> JourneyRecord: ...
    async def profile(self, session: Session, journey_id: UUID) -> ProfileDraftView: ...
    async def update_profile(self, session: Session, journey_id: UUID, draft: ProfileContent, base_revision: int) -> ProfileDraftView: ...
    async def confirm_profile(self, session: Session, journey_id: UUID, draft: ProfileContent, base_revision: int) -> ProfileConfirmResult: ...
    async def resolve_profile(self, session: Session, reference: ProfileRef, *, require_current: bool) -> ResolvedJourneyProfile: ...


class UnavailableJourneyStore:
    async def create(self, *args, **kwargs):
        raise AppError("SERVICE_UNAVAILABLE")

    load = profile = update_profile = confirm_profile = resolve_profile = create


class JourneyService:
    def __init__(self, store: JourneyStore, consents: ConsentService, admission: AdmissionService):
        self.store, self.consents, self.admission = store, consents, admission

    async def create(self, session: Session, identity: InferenceIdentity, key: str, body: JourneyCreate) -> Journey:
        if body.saved_profile is not None:
            # #42/#73의 실제 회원·저장본 소유권 확인 전에는 헤더/본문의 회원 사칭을 받지 않는다.
            raise AppError("UNAUTHENTICATED")
        if identity.subject_id != session.subject_id or identity.account_id is not None:
            raise AppError("NOT_FOUND")
        await self.consents.require(ConsentActor(session.subject_id, session_digest=session.digest), "ai_processing",
                                    notice_version=body.ai_notice_version)
        try:
            key_id = UUID(key)
            if str(key_id) != key.lower():
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AppError("VALIDATION_FAILED") from None
        budget = self.admission.generation_budget(identity)
        record = await self.store.create(session, key_id, input_fingerprint(body.model_dump(mode="json")),
                                         body.ai_notice_version, budget, self.admission.identity_key_id)
        return record.view

    async def load(self, session: Session, journey_id: UUID, *, user_activity: bool = False) -> JourneyRecord:
        consent = await self.consents.require(ConsentActor(session.subject_id, session_digest=session.digest), "ai_processing")
        return await self.store.load(session, journey_id, consent.notice_version, user_activity=user_activity)

    async def profile(self, session: Session, journey_id: UUID) -> ProfileDraftView:
        # 직접 읽기/편집은 모델 호출이 없어 AI 동의를 요구하지 않는다. 저장소가 주체/수명을 재검사한다.
        return await self.store.profile(session, journey_id)

    async def update_profile(self, session: Session, journey_id: UUID, body: ProfileUpdate) -> ProfileDraftView:
        current = await self.profile(session, journey_id)
        if body.base_revision != current.revision:
            raise AppError("VERSION_CONFLICT")
        existing = {item.id for item in current.draft.experiences}
        supplied = [item.id for item in body.draft.experiences if item.id is not None]
        if len(supplied) != len(set(supplied)) or not set(supplied) <= existing:
            raise AppError("VALIDATION_FAILED")
        values = body.draft.model_dump()
        for item in values["experiences"]:
            if item["id"] is None:
                item["id"] = uuid4()
        draft = ProfileContent.model_validate(values)
        if len(draft.model_dump_json().encode("utf-8")) > 65536:
            raise AppError("PAYLOAD_TOO_LARGE")
        return await self.store.update_profile(session, journey_id, draft, body.base_revision)

    async def confirm_profile(self, session: Session, journey_id: UUID, base_revision: int) -> ProfileConfirmResult:
        current = await self.profile(session, journey_id)
        if current.revision != base_revision:
            raise AppError("VERSION_CONFLICT")
        missing = current.draft.missing_for_recommendation()
        if missing:
            raise MissingProfileFields(missing)
        return await self.store.confirm_profile(session, journey_id, current.draft, base_revision)

    async def resolve_profile(self, session: Session, reference: ProfileRef, *, require_current: bool = False) -> ResolvedJourneyProfile:
        if reference.kind != "journey":
            # 실제 회원 저장본 resolver는 인증·저장 구현(#42/#75)에 연결해야 한다.
            raise AppError("UNAUTHENTICATED")
        return await self.store.resolve_profile(session, reference, require_current=require_current)
