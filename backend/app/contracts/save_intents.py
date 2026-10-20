"""로그인 저장 대기: 본문 대신 현재 세션의 승인 참조만 받는다."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt

from app.contracts.fields import CONTRACT_CONFIG
from app.contracts.time import UtcDatetime

Version = Annotated[StrictInt, Field(ge=1, lt=2**31)]


class IntentProfile(BaseModel):
    model_config = CONTRACT_CONFIG
    version: Version


class IntentDraft(BaseModel):
    model_config = CONTRACT_CONFIG
    draft_id: UUID
    revision: Version


class SaveIntentCreate(BaseModel):
    model_config = CONTRACT_CONFIG
    journey_id: UUID
    profile: IntentProfile | None
    draft: IntentDraft | None


class SaveIntentTargets(BaseModel):
    model_config = CONTRACT_CONFIG
    profile: bool
    draft: bool


class SaveIntent(BaseModel):
    model_config = CONTRACT_CONFIG
    save_intent_id: UUID
    expires_at: UtcDatetime
    targets: SaveIntentTargets


class PendingSaveIntent(SaveIntent):
    existing_saved_profile_version: Version | None
