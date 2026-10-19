"""확정 프로필 추천 요청. 선택 필터는 필수 조건을 좁히기만 한다."""

from typing import Annotated

from pydantic import BaseModel, Field, StrictBool, field_validator

from app.contracts.fields import ActivityType, CONTRACT_CONFIG, Unique
from app.contracts.journey import ProfileRef
from app.contracts.regions import Region


class RecommendationFilters(BaseModel):
    model_config = CONTRACT_CONFIG

    activity_types: Annotated[list[ActivityType], Field(min_length=1), Unique] | None = None
    regions: Annotated[list[Region], Field(min_length=1, max_length=10)] | None = None
    paid: StrictBool | None = None

    @field_validator("activity_types", "regions", "paid")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("선택 필터는 생략하거나 값을 지정해야 합니다")
        return value


class RecommendationRequest(BaseModel):
    model_config = CONTRACT_CONFIG

    profile: ProfileRef
    filters: RecommendationFilters
