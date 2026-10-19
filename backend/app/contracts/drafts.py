"""체험 지원서 계약. 사용자 승인과 회원 저장을 구분한다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, StrictInt, StrictStr, model_validator

from app.contracts.fields import CONTRACT_CONFIG, _text_checker, text
from app.contracts.preparation import OpportunityRef
from app.contracts.time import UtcDatetime

DraftMode = Literal['generate', 'manual', 'from_saved']
DraftText = Annotated[StrictStr, Field(max_length=2000), AfterValidator(lambda value: '' if value == '' else _text_checker(True)(value))]
ReviewReason = Literal['profile_changed', 'opportunity_changed', 'opportunity_closed']


class SavedDocumentRef(BaseModel):
    model_config = CONTRACT_CONFIG
    document_id: UUID
    version: Annotated[StrictInt, Field(ge=1)]


class DraftCreate(BaseModel):
    model_config = CONTRACT_CONFIG
    profile_version: Annotated[StrictInt, Field(ge=1)]
    opportunity: OpportunityRef
    mode: DraftMode
    saved_document: SavedDocumentRef | None

    @model_validator(mode='after')
    def _source(self):
        if (self.mode == 'from_saved') != (self.saved_document is not None):
            raise ValueError('저장 문서 참조를 확인해 주세요')
        return self


class JourneyDraft(BaseModel):
    model_config = CONTRACT_CONFIG
    draft_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    mode: DraftMode
    profile_version: Annotated[StrictInt, Field(ge=1)]
    opportunity: OpportunityRef
    self_introduction: DraftText
    motivation: DraftText
    approved_at: UtcDatetime | None
    review_reasons: list[ReviewReason]
    warnings: Annotated[list[text(300)], Field(max_length=10)]
