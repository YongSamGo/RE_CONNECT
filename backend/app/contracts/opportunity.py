"""공고 내용 계약 (Plan/02 §3, openapi `OpportunityInput`).

운영자 등록·수정과 수집기 정규화 결과가 같은 타입을 쓴다. 저장하면 새 `pending` 버전이 되고,
버전·검수 상태·확인 시각·해시는 서버가 붙인다(#17).

- `description_text`: 공식 원문 설명(일반 텍스트). 정규화 후 5,000자를 넘으면 수집기가 앞부분만 넣고
  `description_truncated=true`로 저장한다(#46). 원문에 없으면 null이며 설명을 만들어 채우지 않는다.
- 선택 텍스트에 값이 없으면 빈 문자열이 아니라 null을 넣는다. 공백뿐인 값은 거절한다.
- `deadline_date`와 `deadline_at`이 함께 있으면 같은 한국 날짜여야 한다. 원문의 날짜와 시각이 서로 맞지 않으면
  수집기는 `deadline_at`을 null로 두고 날짜만 넣는다. 새 버전은 어차피 `pending`이므로 검수에서 확인한다.
- URL은 `https`이고 계정정보·백슬래시·제어 문자·fragment가 없는 주소만 받는다. 출처별 공식 경로 허용표는 수집기·검수가 맡는다.
- `requirements`: 빈 배열은 "명시된 필수조건 없음"으로 검수한 상태다. 해석하지 못한 조건은 `field=other`로 남긴다.
"""

import re
from datetime import date, datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, Field, StrictBool, StrictStr, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.contracts.fields import CONTRACT_CONFIG, ActivityType, HoursPerWeek, SkillTag, Unique, text
from app.contracts.regions import Region
from app.contracts.requirement import Requirement, find_group_conflicts
from app.contracts.time import UtcDatetime, kst_date

DESCRIPTION_MAX_LENGTH = 5000

ApplicationMethod = Literal["online", "phone", "visit", "email", "mixed"]
RecruitmentStatus = Literal["open", "closed", "unknown"]

# 역할 사전(RoleDefinition)의 키. 사전에 있는지는 저장할 때 확인한다(#17).
RoleId = Annotated[StrictStr, Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")]
_HOSTNAME_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def _check_https_url(value: str) -> str:
    """접두사만 보면 `https://공식주소@다른주소/`처럼 실제 호스트를 가린 주소가 통과한다. 나눠서 확인한다."""
    if not value.isascii() or not value.isprintable() or " " in value or "\\" in value:
        raise _invalid_url()
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise _invalid_url() from None
    hostname = parts.hostname or ""
    if (
        parts.scheme != "https"
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
        or "@" in parts.netloc
        or port is not None and port != 443
        or "." not in hostname
        or not all(_HOSTNAME_LABEL.fullmatch(label) for label in hostname.split("."))
    ):
        raise _invalid_url()
    return value


def _invalid_url() -> PydanticCustomError:
    return PydanticCustomError("invalid_url", "받을 수 없는 주소")


HttpsUrl = Annotated[StrictStr, Field(max_length=2000), AfterValidator(_check_https_url)]
_Text = text(500, multiline=True)


class OpportunityContent(BaseModel):
    model_config = CONTRACT_CONFIG

    title: text(200)
    organization_name: text(200)
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
    description_text: text(DESCRIPTION_MAX_LENGTH, multiline=True) | None
    requirements: Annotated[list[Requirement], Field(max_length=30)]
    required_documents: Annotated[list[text(200)], Field(max_length=20)] | None
    application_method: ApplicationMethod
    application_instructions: text(2000, multiline=True)
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

    @field_validator("deadline_at")
    @classmethod
    def _deadline_pair_matches(cls, deadline_at: datetime | None, info: ValidationInfo) -> datetime | None:
        deadline_date = info.data.get("deadline_date")
        if deadline_at is not None and deadline_date is not None and kst_date(deadline_at) != deadline_date:
            raise PydanticCustomError("deadline_mismatch", "마감 날짜와 마감 시각의 한국 날짜가 다르다")
        return deadline_at
