"""JourneyCreate/Journey/Message 공개 계약. 승인·소유자는 요청에서 받지 않는다."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt

from app.contracts.fields import CONTRACT_CONFIG, text
from app.contracts.time import UtcDatetime

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
    id: UUID
    version: Annotated[StrictInt, Field(ge=1)]


class Journey(BaseModel):
    model_config = CONTRACT_CONFIG
    journey_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    expires_at: UtcDatetime
    idle_expires_at: UtcDatetime
    first_message: Message
    confirmed: ConfirmedVersion | None
