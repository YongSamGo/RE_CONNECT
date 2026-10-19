"""자격 대조 요청/응답. 조건 피연산자와 실제 사용자 값의 형태를 분리한다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, StrictFloat, StrictInt

from app.contracts.fields import CONTRACT_CONFIG, text
from app.contracts.journey import ProfileRef
from app.contracts.preparation import OpportunityRef
from app.contracts.regions import Region
from app.contracts.requirement import GroupOperator, RequirementField
from app.contracts.time import UtcDatetime

EligibilityStatus = Literal["satisfied", "not_satisfied", "unknown"]
ReviewReason = Literal["missing_profile_value", "unclear_requirement", "age_boundary", "reference_date_missing", "unsupported_group"]
# 프로필의 빈 배열은 없음 확인이며 null과 다르다. 거주지는 단일 Region이다.
EligibilityUserValue = (StrictInt | StrictFloat | Region
                        | Annotated[list[StrictInt], Field(max_length=7)]
                        | Annotated[list[text(100)], Field(max_length=20)] | None)


class EligibilityRequest(BaseModel):
    model_config = CONTRACT_CONFIG
    profile: ProfileRef
    opportunity_version: Annotated[StrictInt, Field(ge=1)]


class ConditionEvaluation(BaseModel):
    model_config = CONTRACT_CONFIG
    requirement_id: UUID
    field: RequirementField
    result: EligibilityStatus
    user_value: EligibilityUserValue
    source_evidence: text(1000, multiline=True)
    review_reason: ReviewReason | None


class GroupEvaluation(BaseModel):
    model_config = CONTRACT_CONFIG
    group_id: UUID
    operator: GroupOperator
    result: EligibilityStatus


class EligibilityResult(BaseModel):
    model_config = CONTRACT_CONFIG
    profile: ProfileRef
    opportunity: OpportunityRef
    overall: EligibilityStatus
    no_requirements: StrictBool
    conditions: Annotated[list[ConditionEvaluation], Field(max_length=30)]
    groups: Annotated[list[GroupEvaluation], Field(max_length=30)]
    evaluated_at: UtcDatetime
