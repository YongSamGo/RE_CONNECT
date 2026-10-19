"""JourneyCreate/Journey/Message 공개 계약. 승인·소유자는 요청에서 받지 않는다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt

from app.contracts.fields import CONTRACT_CONFIG, text
from app.contracts.time import UtcDatetime
from app.contracts.profile import ProfileContent, ProfileContentInput, RecommendationField

NoticeVersion = Annotated[str, Field(strict=True, pattern=r"^[a-z0-9._-]{1,32}$", max_length=32)]


class SavedProfileRef(BaseModel):
    model_config = CONTRACT_CONFIG
    profile_id: UUID
    version: Annotated[StrictInt, Field(ge=1)]


class JourneyCreate(BaseModel):
    model_config = CONTRACT_CONFIG
    ai_notice_version: NoticeVersion
    saved_profile: SavedProfileRef | None


class Message(BaseModel):
    model_config = CONTRACT_CONFIG
    message_id: UUID
    text: text(2000, multiline=True)
    created_at: UtcDatetime


class ConfirmedVersion(BaseModel):
    model_config = CONTRACT_CONFIG
    version: Annotated[StrictInt, Field(ge=1)]
    confirmed_at: UtcDatetime


class Journey(BaseModel):
    model_config = CONTRACT_CONFIG
    journey_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    expires_at: UtcDatetime
    idle_expires_at: UtcDatetime
    first_message: Message
    confirmed: ConfirmedVersion | None


class ProfileEvidence(BaseModel):
    model_config = CONTRACT_CONFIG
    path: text(200)
    message_ids: Annotated[list[UUID], Field(min_length=1)]


class ProfileDraftView(BaseModel):
    model_config = CONTRACT_CONFIG
    revision: Annotated[StrictInt, Field(ge=1)]
    draft: ProfileContent
    evidence: list[ProfileEvidence]
    confirmed: ConfirmedVersion | None
    has_unconfirmed_changes: Annotated[bool, Field(strict=True)]
    missing_for_recommendation: list[RecommendationField]


class ProfileUpdate(BaseModel):
    model_config = CONTRACT_CONFIG
    draft: ProfileContentInput
    base_revision: Annotated[StrictInt, Field(ge=1, lt=2**31 - 1)]


class BaseRevision(BaseModel):
    model_config = CONTRACT_CONFIG
    base_revision: Annotated[StrictInt, Field(ge=1, lt=2**31 - 1)]


class ProfileRef(BaseModel):
    model_config = CONTRACT_CONFIG
    kind: Literal["journey", "saved"]
    id: UUID
    version: Annotated[StrictInt, Field(ge=1)]


class ProfileConfirmResult(BaseModel):
    model_config = CONTRACT_CONFIG
    profile: ProfileRef
    confirmed_at: UtcDatetime
    revision: Annotated[StrictInt, Field(ge=1)]


class MessageCreate(BaseModel):
    model_config = CONTRACT_CONFIG
    text: text(2000, multiline=True)
    transcription_id: UUID | None
    base_revision: Annotated[StrictInt, Field(ge=1, lt=2**31 - 1)]


class MessageResult(BaseModel):
    model_config = CONTRACT_CONFIG
    revision: Annotated[StrictInt, Field(ge=1)]
    user_message_id: UUID
    assistant_message: Message | None
    profile: ProfileDraftView
    notices: Annotated[list[text(300)], Field(max_length=10)]
    next_step: Literal['continue', 'review_profile']


class ConversationTurn(BaseModel):
    """소유 체험의 내부 문맥. 공개 대화 복원 API로 노출하지 않는다."""
    model_config = CONTRACT_CONFIG
    message_id: UUID
    text: text(2000, multiline=True)


class MessageCommit(BaseModel):
    """완료 스크립트에서 본문/초안/멱등 응답을 함께 쓰는 내부 자료."""
    model_config = CONTRACT_CONFIG
    response: MessageResult
    turns: Annotated[list[ConversationTurn], Field(min_length=1, max_length=64)]
