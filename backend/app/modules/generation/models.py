"""LLM 내부 출력 계약. 공개 API 계약이나 사용자 승인 상태가 아니다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt

from app.contracts.fields import CONTRACT_CONFIG, Unique, text
from app.contracts.profile import ExperienceInput, ProfileContent, RecommendationField
from app.contracts.preparation import OpportunityRef


class Quote(BaseModel):
    model_config = CONTRACT_CONFIG

    turn_index: Annotated[StrictInt, Field(ge=0, le=63)]
    text: text(1000, multiline=True)


class ExperienceSelection(BaseModel):
    model_config = CONTRACT_CONFIG

    existing_id: UUID | None
    description: Quote
    duration: Quote | None
    skills: Annotated[list[Quote], Field(max_length=20)]


class ExtractionPlan(BaseModel):
    model_config = CONTRACT_CONFIG

    experiences: Annotated[list[ExperienceSelection], Field(max_length=20)]


class ExperiencePreview(BaseModel):
    model_config = CONTRACT_CONFIG

    experiences: Annotated[list[ExperienceInput], Field(max_length=20)]
    excluded_turn_indices: Annotated[list[StrictInt], Field(max_length=64)]
    # 원문 근거가 있다는 것과 사실 승인은 다르다. 서버가 정하는 고정값이다.
    requires_confirmation: Literal[True] = True


class QuestionPlan(BaseModel):
    model_config = CONTRACT_CONFIG

    field: RecommendationField


class ApplicationPlan(BaseModel):
    model_config = CONTRACT_CONFIG

    # 모델은 문장을 쓰지 않고 서버의 확정 사실 ID만 선택한다.
    fact_ids: Annotated[list[text(80)], Field(min_length=1, max_length=30), Unique]


class ConfirmedProfileSnapshot(BaseModel):
    """호출자가 소유권·확정을 확인한 뒤 전달하는 스냅샷. HTTP 입력에 쓰지 않는다."""

    model_config = CONTRACT_CONFIG

    profile_id: UUID
    version: Annotated[StrictInt, Field(ge=1)]
    content: ProfileContent


class ApplicationPreview(BaseModel):
    model_config = CONTRACT_CONFIG

    profile_id: UUID
    profile_version: Annotated[StrictInt, Field(ge=1)]
    paragraphs: Annotated[list[text(2000, multiline=True)], Field(max_length=30)]
    requires_confirmation: Literal[True] = True


class ApplicationContext(BaseModel):
    """공개·버전 검사를 마친 공고. 확정 개인 사실로 승격하지 않는다."""
    model_config = CONTRACT_CONFIG
    opportunity: OpportunityRef
    title: text(200)
    description: text(5000, multiline=True) | None
