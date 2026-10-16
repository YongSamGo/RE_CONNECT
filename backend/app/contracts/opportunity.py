"""공고 내용 계약 (Plan/02 §3, openapi `OpportunityInput`).

운영자 등록·수정과 수집기 정규화 결과가 같은 타입을 쓴다. 저장하면 새 `pending` 버전이 되고,
버전·검수 상태·확인 시각·해시는 서버가 붙인다(#17).

- `description_text`: 공식 원문 설명(일반 텍스트). 정규화 후 5,000자를 넘으면 수집기가 앞부분만 넣고
  `description_truncated=true`로 저장한다(#46). 원문에 없으면 null이며 설명을 만들어 채우지 않는다.
- `requirements`: 빈 배열은 "명시된 필수조건 없음"으로 검수한 상태다. 해석하지 못한 조건은 `field=other`로 남긴다.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictBool, StrictStr, field_validator
from pydantic_core import PydanticCustomError

from app.contracts.fields import CONTRACT_CONFIG, ActivityType, HoursPerWeek, SkillTag, Unique
from app.contracts.regions import Region
from app.contracts.requirement import Requirement, find_group_conflicts
from app.contracts.time import UtcDatetime

DESCRIPTION_MAX_LENGTH = 5000

ApplicationMethod = Literal["online", "phone", "visit", "email", "mixed"]
RecruitmentStatus = Literal["open", "closed", "unknown"]

# 역할 사전(RoleDefinition)의 키. 사전에 있는지는 저장할 때 확인한다(#17).
RoleId = Annotated[StrictStr, Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")]
HttpsUrl = Annotated[StrictStr, Field(max_length=2000, pattern=r"^https://[^\s/?#]+[^\s]*$")]
_Text = Annotated[StrictStr, Field(max_length=500)]


class OpportunityContent(BaseModel):
    model_config = CONTRACT_CONFIG

    title: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    organization_name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    activity_type: ActivityType
    is_public_job: StrictBool | None
    role_tags: Annotated[list[RoleId], Field(max_length=10), Unique]
    skill_tags: Annotated[list[SkillTag], Field(max_length=20), Unique]
    # 원격이 아닌 공고의 활동 지역. 모르면 null(지역 기준 추천에서 제외)
    activity_region: Region | None
    location_text: _Text | None
    remote_allowed: StrictBool | None
    schedule_text: _Text | None
    hours_per_week: HoursPerWeek | None
    paid: StrictBool | None
    compensation_text: _Text | None
    description_text: Annotated[StrictStr, Field(max_length=DESCRIPTION_MAX_LENGTH)] | None
    requirements: Annotated[list[Requirement], Field(max_length=30)]
    required_documents: Annotated[list[Annotated[StrictStr, Field(min_length=1, max_length=200)]], Field(max_length=20)] | None
    application_method: ApplicationMethod
    application_instructions: Annotated[StrictStr, Field(min_length=1, max_length=2000)]
    source_url: HttpsUrl
    application_url: HttpsUrl
    # 날짜만 제공된 마감(한국 날짜). 시각을 만들어 붙이지 않는다
    deadline_date: date | None
    # 공식 시각이 제공된 경우에만
    deadline_at: UtcDatetime | None
    recruitment_status: RecruitmentStatus

    @field_validator("requirements")
    @classmethod
    def _groups_consistent(cls, requirements: list[Requirement]) -> list[Requirement]:
        if find_group_conflicts(requirements):
            raise PydanticCustomError("group_conflict", "같은 그룹의 연산자가 다르다")
        return requirements
