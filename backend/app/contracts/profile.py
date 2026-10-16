"""프로필·경험 계약 (Plan/02 §2, openapi `ProfileContent`·`ProfileContentInput`).

- 선택 항목도 키를 보내야 한다. 키가 없으면 `required`로 거절한다(기본값을 두지 않는다).
- `null`은 미확인, 빈 배열은 "없다고 확인함"이다. 예외로 `experiences`·`preferred_regions`·`activity_types`는
  `null`을 허용하지 않고 빈 배열이 "아직 입력하지 않음"이다. 추천 전에 `missing_for_recommendation`으로 다시 묻는다.
- 확정 여부·확정 시각·소유자·버전은 여기 없다. 서버가 따로 관리하고 클라이언트·AI가 보낸 값을 믿지 않는다.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt, StrictStr, field_validator
from pydantic_core import PydanticCustomError

from app.contracts.fields import CONTRACT_CONFIG, ActivityType, HoursPerWeek, SkillTag, Unique, Weekday
from app.contracts.regions import Region
from app.contracts.time import kst_today

PROFILE_SCHEMA_VERSION = 1

PaidPreference = Literal["paid", "unpaid", "any"]
# 추천에 1개 이상 필요한 항목. 비어 있으면 missing_for_recommendation에 넣는다.
RecommendationField = Literal["experiences", "preferred_regions", "activity_types"]

_ShortText = Annotated[StrictStr, Field(min_length=1, max_length=100)]


class _ExperienceBase(BaseModel):
    model_config = CONTRACT_CONFIG

    description: Annotated[StrictStr, Field(min_length=1, max_length=1000)]
    skill_tags: Annotated[list[SkillTag], Field(max_length=20), Unique]
    # 사용자가 말한 기간. 불명확하면 추정하지 않고 null
    duration_note: Annotated[StrictStr, Field(max_length=200)] | None


class Experience(_ExperienceBase):
    id: UUID


class ExperienceInput(_ExperienceBase):
    """초안 수정 요청용. 새 경험은 id를 null로 보내고 서버가 부여한다."""

    id: UUID | None


class _ProfileContentBase(BaseModel):
    model_config = CONTRACT_CONFIG

    schema_version: Literal[1]
    skills: Annotated[list[SkillTag], Field(max_length=30), Unique]
    preferred_regions: Annotated[list[Region], Field(max_length=10)]
    activity_types: Annotated[list[ActivityType], Field(max_length=2), Unique]
    paid_preference: PaidPreference | None
    available_weekdays: Annotated[list[Weekday], Field(max_length=7), Unique] | None
    hours_per_week: HoursPerWeek | None
    mobility_note: Annotated[StrictStr, Field(max_length=300)] | None
    # 거주 자격 대조용. 희망 활동 지역과 다르다
    residence_region: Region | None
    birth_year: Annotated[StrictInt, Field(ge=1900)] | None
    certifications: Annotated[list[_ShortText], Field(max_length=20)] | None
    completed_courses: Annotated[list[_ShortText], Field(max_length=20)] | None
    # 활동 수행 조건. 진단명·상세 병력은 받지 않는다
    activity_constraints: Annotated[list[Annotated[StrictStr, Field(min_length=1, max_length=200)]], Field(max_length=10)] | None

    @field_validator("birth_year")
    @classmethod
    def _birth_year_not_future(cls, birth_year: int | None) -> int | None:
        if birth_year is not None and birth_year > kst_today().year:
            raise PydanticCustomError("less_than_equal", "올해보다 뒤의 출생연도")
        return birth_year

    def missing_for_recommendation(self) -> list[RecommendationField]:
        fields: tuple[RecommendationField, ...] = ("experiences", "preferred_regions", "activity_types")
        return [name for name in fields if not getattr(self, name)]


class ProfileContent(_ProfileContentBase):
    experiences: Annotated[list[Experience], Field(max_length=20)]


class ProfileContentInput(_ProfileContentBase):
    experiences: Annotated[list[ExperienceInput], Field(max_length=20)]
