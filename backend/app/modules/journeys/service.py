"""생성·조회·활동 수명. 모델 호출·자동 승인·저장 프로필 사칭을 허용하지 않는다."""

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from app.contracts.journey import Journey, JourneyCreate
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


class JourneyStore(Protocol):
    async def create(self, session: Session, key_id: UUID, fingerprint: str, notice_version: str,
                     budget: str, key_id_digest: str) -> JourneyRecord: ...
    async def load(self, session: Session, journey_id: UUID, notice_version: str, *, user_activity: bool) -> JourneyRecord: ...


class UnavailableJourneyStore:
    async def create(self, *args, **kwargs):
        raise AppError("SERVICE_UNAVAILABLE")

    load = create


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
