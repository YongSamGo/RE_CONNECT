"""현재 회원의 확정 프로필 저장 계약. 본문·소유자를 요청으로 받지 않는다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt

from app.contracts.fields import CONTRACT_CONFIG
from app.contracts.profile import ProfileContent
from app.contracts.time import UtcDatetime

Version = Annotated[StrictInt, Field(ge=1, lt=2**31)]


class JourneyProfileSource(BaseModel):
    model_config = CONTRACT_CONFIG
    type: Literal['journey']
    journey_id: UUID
    version: Version


class IntentProfileSource(BaseModel):
    model_config = CONTRACT_CONFIG
    type: Literal['save_intent']
    save_intent_id: UUID


class ProfileSaveRequest(BaseModel):
    model_config = CONTRACT_CONFIG
    source: Annotated[JourneyProfileSource | IntentProfileSource, Field(discriminator='type')]
    base_saved_version: Version | None


class ProfileSaveResult(BaseModel):
    model_config = CONTRACT_CONFIG
    version: Version
    saved_at: UtcDatetime
    created: bool
    replaced_version: Version | None


class SavedProfile(BaseModel):
    model_config = CONTRACT_CONFIG
    profile_id: UUID
    version: Version
    confirmed_at: UtcDatetime
    saved_at: UtcDatetime
    content: ProfileContent


class SavedProfileResponse(BaseModel):
    model_config = CONTRACT_CONFIG
    saved: SavedProfile | None
