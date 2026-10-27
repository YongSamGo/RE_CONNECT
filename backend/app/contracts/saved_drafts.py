"""승인 지원서 저장·자기 목록/상세. 승인 본문을 요청으로 받지 않는다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.contracts.drafts import DraftText, ReviewReason
from app.contracts.fields import CONTRACT_CONFIG, text
from app.contracts.preparation import OpportunityRef
from app.contracts.saved_profiles import IntentProfileSource, Version
from app.contracts.time import UtcDatetime


class JourneyDraftSource(BaseModel):
    model_config = CONTRACT_CONFIG
    type: Literal['journey']
    journey_id: UUID
    draft_id: UUID
    revision: Version


class DraftSaveRequest(BaseModel):
    model_config = CONTRACT_CONFIG
    source: Annotated[JourneyDraftSource | IntentProfileSource, Field(discriminator='type')]
    document_id: UUID | None
    base_document_version: Version | None

    @model_validator(mode='after')
    def paired(self):
        if (self.document_id is None) != (self.base_document_version is None):
            raise ValueError('문서와 기준 버전을 함께 지정해 주세요')
        return self


class DraftSaveResult(BaseModel):
    model_config = CONTRACT_CONFIG
    document_id: UUID
    version: Version
    saved_at: UtcDatetime
    profile_version: Version


class SavedDraftBody(BaseModel):
    model_config = CONTRACT_CONFIG
    self_introduction: DraftText
    motivation: DraftText


class SavedDraftSummary(BaseModel):
    model_config = CONTRACT_CONFIG
    document_id: UUID
    version: Version
    opportunity: OpportunityRef
    opportunity_title: text(200)
    organization_name: text(200)
    saved_at: UtcDatetime
    review_reasons: list[ReviewReason]


class SavedDraft(SavedDraftSummary, SavedDraftBody):
    profile_version: Version
    approved_at: UtcDatetime


class SavedDraftList(BaseModel):
    model_config = CONTRACT_CONFIG
    items: Annotated[list[SavedDraftSummary], Field(max_length=20)]
    page: int
    page_size: int
    total: int
