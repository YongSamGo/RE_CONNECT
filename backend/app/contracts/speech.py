"""클라이언트 자유 문장 대신 서버 자료의 버전 참조만 읽는다."""

from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, Field, StrictInt
from app.contracts.fields import CONTRACT_CONFIG

DraftField = Literal['self_introduction', 'motivation']


class SpeechOpportunity(BaseModel):
    model_config = CONTRACT_CONFIG
    kind: Literal['opportunity']
    opportunity_id: UUID
    version: Annotated[StrictInt, Field(ge=1)]
    field: Literal['title', 'description_text', 'schedule_text', 'location_text', 'compensation_text', 'application_instructions']


class SpeechJourneyMessage(BaseModel):
    model_config = CONTRACT_CONFIG
    kind: Literal['journey_message']
    journey_id: UUID
    message_id: UUID


class SpeechJourneyDraft(BaseModel):
    model_config = CONTRACT_CONFIG
    kind: Literal['journey_draft']
    journey_id: UUID
    draft_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    field: DraftField


class SpeechSavedDraft(BaseModel):
    model_config = CONTRACT_CONFIG
    kind: Literal['saved_draft']
    document_id: UUID
    version: Annotated[StrictInt, Field(ge=1)]
    field: DraftField


class SpeechRequest(BaseModel):
    model_config = CONTRACT_CONFIG
    target: Annotated[SpeechOpportunity | SpeechJourneyMessage | SpeechJourneyDraft | SpeechSavedDraft, Field(discriminator='kind')]
    segment: Annotated[StrictInt, Field(ge=0)]
