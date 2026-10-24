"""생성·조회·활동 수명. 모델 호출·자동 승인·저장 프로필 사칭을 허용하지 않는다."""

from dataclasses import dataclass, field
import json
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4
from pydantic import TypeAdapter, ValidationError

from app.contracts.journey import Journey, JourneyCreate, ProfileDraftView, ProfileUpdate, ProfileRef, ProfileConfirmResult, ConversationTurn, MessageResult
from app.contracts.profile import ProfileContent
from app.contracts.roles import RoleExclusions
from app.core.business_errors import AppError
from app.modules.admission.service import AdmissionService, InferenceIdentity
from app.modules.consents.service import ConsentActor, ConsentService
from app.modules.requests.service import CompletionGuard, ResultReference, input_fingerprint
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


@dataclass(frozen=True)
class RoleState:
    revision: int
    profile_version: int
    role_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProfileDependency:
    """지원서 조회용 표시 정보. 원래 근거 참조·본문·승인을 갱신하지 않는다."""

    reference: ProfileRef
    current_profile: ProfileRef
    review_reasons: tuple[Literal["profile_changed"], ...]
    based_on_previous_confirmed: bool


class JourneyStore(Protocol):
    async def question(self, session: Session, journey_id: UUID, notice_version: str, message_id: UUID): ...
    async def message_data(self, session: Session, journey_id: UUID, notice_version: str, field: str) -> str: ...
    async def end(self, session: Session, journey_id: UUID) -> None: ...
    async def create(self, session: Session, key_id: UUID, fingerprint: str, notice_version: str,
                     budget: str, key_id_digest: str, *, initial_profile: ProfileContent | None = None,
                     confirmed_at: datetime | None = None) -> JourneyRecord: ...
    async def load(self, session: Session, journey_id: UUID, notice_version: str, *, user_activity: bool) -> JourneyRecord: ...
    async def profile(self, session: Session, journey_id: UUID) -> ProfileDraftView: ...
    async def update_profile(self, session: Session, journey_id: UUID, draft: ProfileContent, base_revision: int) -> ProfileDraftView: ...
    async def confirm_profile(self, session: Session, journey_id: UUID, draft: ProfileContent, base_revision: int) -> ProfileConfirmResult: ...
    async def resolve_profile(self, session: Session, reference: ProfileRef, *, require_current: bool) -> ResolvedJourneyProfile: ...
    async def role_state(self, session: Session, journey_id: UUID) -> RoleState: ...
    async def set_role_exclusions(self, session: Session, journey_id: UUID, role_ids: list[str], base_revision: int) -> RoleExclusions: ...


class UnavailableJourneyStore:
    session_transition_managed = True  # 실제 자료를 생성/보관하지 않는 실패 닫기 저장소.

    async def create(self, *args, **kwargs):
        raise AppError("SERVICE_UNAVAILABLE")

    question = message_data = end = load = profile = update_profile = confirm_profile = resolve_profile = role_state = set_role_exclusions = create


class JourneyService:
    @property
    def session_transition_managed(self):
        return getattr(self.store, 'session_transition_managed', False)

    def __init__(self, store: JourneyStore, consents: ConsentService, admission: AdmissionService):
        self.store, self.consents, self.admission = store, consents, admission
        self.stored_profiles = None

    async def end(self, session: Session, journey_id: UUID) -> None:
        await self.store.end(session, journey_id)

    async def create(self, session: Session, identity: InferenceIdentity, key: str, body: JourneyCreate) -> Journey:
        if body.saved_profile is not None and (session.user_id is None or self.stored_profiles is None):
            raise AppError("UNAUTHENTICATED")
        if identity.subject_id != session.subject_id or identity.account_id != session.user_id:
            raise AppError("NOT_FOUND")
        actor = ConsentActor(session.subject_id, member_id=session.user_id, session_digest=session.digest, member_generation=session.user_generation)
        await self.consents.require(actor, "ai_processing",
                                    notice_version=body.ai_notice_version)
        await self.consents.bind_session(actor, body.ai_notice_version)
        try:
            key_id = UUID(key)
            if str(key_id) != key.lower():
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AppError("VALIDATION_FAILED") from None
        budget = self.admission.generation_budget(identity)
        if body.saved_profile is not None:
            async def create(source):
                return await self.store.create(session, key_id, input_fingerprint(body.model_dump(mode='json')),
                    body.ai_notice_version, budget, self.admission.identity_key_id,
                    initial_profile=source.content, confirmed_at=source.confirmed_at)
            record = await self.stored_profiles.start_journey(session, body.saved_profile, body.ai_notice_version, create)
            return record.view
        record = await self.store.create(session, key_id, input_fingerprint(body.model_dump(mode="json")),
                                         body.ai_notice_version, budget, self.admission.identity_key_id)
        return record.view

    async def load(self, session: Session, journey_id: UUID, *, user_activity: bool = False) -> JourneyRecord:
        actor = ConsentActor(session.subject_id, member_id=session.user_id, session_digest=session.digest, member_generation=session.user_generation)
        consent = await self.consents.require(actor, "ai_processing")
        await self.consents.bind_session(actor, consent.notice_version)
        return await self.store.load(session, journey_id, consent.notice_version, user_activity=user_activity)

    async def profile(self, session: Session, journey_id: UUID) -> ProfileDraftView:
        # 직접 읽기/편집은 모델 호출이 없어 AI 동의를 요구하지 않는다. 저장소가 주체/수명을 재검사한다.
        return await self.store.profile(session, journey_id)

    async def question(self, session: Session, journey_id: UUID, message_id: UUID):
        record = await self.load(session, journey_id)
        if record.view.first_message.message_id == message_id:
            return record.view.first_message
        return await self.store.question(session, journey_id, record.guard.ai_notice_version, message_id)

    async def conversation(self, session: Session, journey_id: UUID, notice_version: str) -> list[ConversationTurn]:
        try:
            raw = await self.store.message_data(session, journey_id, notice_version, 'conversation')
            turns = TypeAdapter(list[ConversationTurn]).validate_python(json.loads(raw))
            if len(turns) > 64 or sum(len(turn.text.encode('utf-8')) for turn in turns) > 12000:
                raise ValueError
            if len({turn.message_id for turn in turns}) != len(turns):
                raise ValueError
            return turns
        except (ValueError, TypeError, ValidationError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def message_result(self, session: Session, journey_id: UUID, notice_version: str, reference: ResultReference) -> MessageResult:
        if reference.kind != 'message':
            raise AppError('SERVICE_UNAVAILABLE')
        raw = await self.store.message_data(session, journey_id, notice_version, f'message_result:{reference.id}')
        try:
            response = MessageResult.model_validate_json(raw)
            if response.user_message_id != reference.id or response.revision != reference.version:
                raise ValueError
            return response
        except (ValueError, TypeError, ValidationError):
            raise AppError('SERVICE_UNAVAILABLE') from None

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

    async def role_state(self, session: Session, journey_id: UUID) -> RoleState:
        return await self.store.role_state(session, journey_id)

    async def profile_dependency(self, session: Session, reference: ProfileRef) -> ProfileDependency:
        # 참조한 옛 버전의 실재성과 소유권부터 확인한다. 클라이언트의 버전 비교만 믿지 않는다.
        snapshot = await self.resolve_profile(session, reference, require_current=False)
        current = await self.profile(session, reference.id)
        if current.confirmed is None:
            raise AppError("PROFILE_NOT_CONFIRMED")
        latest = ProfileRef(kind=reference.kind, id=reference.id, version=current.confirmed.version)
        return ProfileDependency(snapshot.reference, latest,
            ("profile_changed",) if snapshot.reference.version != latest.version else (),
            current.has_unconfirmed_changes)

    async def set_role_exclusions(self, session: Session, journey_id: UUID, role_ids: list[str], base_revision: int) -> RoleExclusions:
        return await self.store.set_role_exclusions(session, journey_id, role_ids, base_revision)
