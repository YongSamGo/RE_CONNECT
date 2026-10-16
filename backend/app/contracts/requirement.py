"""공고 자격조건 계약 (Plan/02 §4 Requirement, openapi `Requirement`).

필드별 허용 연산과 값:

| field | operator | value |
|---|---|---|
| age | gte, lte | integer (만 나이) |
| age | between | [min, max] integer 2개, min ≤ max |
| residence_region | in | Region[] 1~30개 |
| certification, completed_course | has_all, has_any | string[] 1~20개 |
| weekday | includes_all, includes_any | integer[] 1~7개, 1=월 ~ 7=일, 중복 없음 |
| hours_per_week | gte, lte | number 0~168 |
| other | null | null (clarity=needs_review) |

표에 없는 조합은 거절한다. 해석하지 못한 조건은 `field=other`, `clarity=needs_review`와 원문 근거로 보존하고,
다른 field에서 operator·value를 null로 두는 것은 허용하지 않는다.
`group_id`와 `group_operator`는 함께 있거나 함께 없어야 한다. 같은 그룹 안의 연산자 일치는 공고 단위에서 검사한다.
`reference_date`가 없는 연령 조건은 받아 두고, 판정(#58)에서 `unknown`으로 처리한다.
"""

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    StrictInt,
    StrictStr,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from app.contracts.fields import CONTRACT_CONFIG, HoursPerWeek, Unique, Weekday
from app.contracts.regions import Region

RequirementField = Literal[
    "age",
    "residence_region",
    "certification",
    "completed_course",
    "weekday",
    "hours_per_week",
    "other",
]
RequirementOperator = Literal["gte", "lte", "between", "in", "has_all", "has_any", "includes_all", "includes_any"]
GroupOperator = Literal["and", "or"]
Clarity = Literal["clear", "needs_review"]

Age = Annotated[StrictInt, Field(ge=0, le=150)]
_ConditionText = Annotated[StrictStr, Field(min_length=1, max_length=100)]

_AGE = TypeAdapter(Age)
_AGE_RANGE = TypeAdapter(Annotated[list[Age], Field(min_length=2, max_length=2)])
_REGIONS = TypeAdapter(Annotated[list[Region], Field(min_length=1, max_length=30)])
_TEXTS = TypeAdapter(Annotated[list[_ConditionText], Field(min_length=1, max_length=20)])
_WEEKDAYS = TypeAdapter(Annotated[list[Weekday], Field(min_length=1, max_length=7), Unique])
_HOURS = TypeAdapter(HoursPerWeek)

# field → 허용 operator → 값 검증기. 여기 없는 조합은 거절한다.
ALLOWED_OPERATORS: dict[RequirementField, dict[RequirementOperator, TypeAdapter[Any]]] = {
    "age": {"gte": _AGE, "lte": _AGE, "between": _AGE_RANGE},
    "residence_region": {"in": _REGIONS},
    "certification": {"has_all": _TEXTS, "has_any": _TEXTS},
    "completed_course": {"has_all": _TEXTS, "has_any": _TEXTS},
    "weekday": {"includes_all": _WEEKDAYS, "includes_any": _WEEKDAYS},
    "hours_per_week": {"gte": _HOURS, "lte": _HOURS},
    "other": {},
}

RequirementValue = int | float | list[int] | list[str] | list[Region] | None


def _invalid() -> PydanticCustomError:
    return PydanticCustomError("invalid_requirement", "허용표에 없는 조건")


class Requirement(BaseModel):
    # 아래 검증기가 앞 필드 값(info.data)을 쓰므로 필드 순서를 바꾸지 않는다.
    model_config = CONTRACT_CONFIG

    id: UUID
    field: RequirementField
    operator: RequirementOperator | None
    value: Any
    group_id: UUID | None
    group_operator: GroupOperator | None
    reference_date: date | None
    source_evidence: Annotated[StrictStr, Field(min_length=1, max_length=1000)]
    clarity: Clarity

    @field_validator("operator")
    @classmethod
    def _operator_allowed(cls, operator: RequirementOperator | None, info: ValidationInfo) -> RequirementOperator | None:
        field = info.data.get("field")
        if field is None:
            return operator
        if field == "other":
            if operator is not None:
                raise _invalid()
        elif operator not in ALLOWED_OPERATORS[field]:
            raise _invalid()
        return operator

    @field_validator("value")
    @classmethod
    def _value_matches_operator(cls, value: Any, info: ValidationInfo) -> RequirementValue:
        field = info.data.get("field")
        # field·operator가 이미 틀렸으면 그 오류만 낸다.
        if field is None or "operator" not in info.data:
            return value
        if field == "other":
            if value is not None:
                raise _invalid()
            return None
        operator: RequirementOperator = info.data["operator"]
        try:
            parsed = ALLOWED_OPERATORS[field][operator].validate_python(value, strict=True)
        except ValidationError:
            raise _invalid() from None
        if operator == "between" and parsed[0] > parsed[1]:
            raise _invalid()
        return parsed

    @field_validator("group_operator")
    @classmethod
    def _group_pair(cls, group_operator: GroupOperator | None, info: ValidationInfo) -> GroupOperator | None:
        if "group_id" not in info.data:
            return group_operator
        has_group = info.data["group_id"] is not None
        if has_group and group_operator is None:
            raise PydanticCustomError("required_with", "group_id가 있으면 group_operator가 필요하다")
        if not has_group and group_operator is not None:
            raise _invalid()
        return group_operator

    @field_validator("clarity")
    @classmethod
    def _other_needs_review(cls, clarity: Clarity, info: ValidationInfo) -> Clarity:
        if info.data.get("field") == "other" and clarity != "needs_review":
            raise _invalid()
        return clarity


def find_group_conflicts(requirements: list[Requirement]) -> list[int]:
    """같은 group_id인데 group_operator가 다른 조건의 위치. 임의로 평탄화하지 않고 거절한다."""
    first_operator: dict[UUID, GroupOperator] = {}
    conflicts: list[int] = []
    for index, requirement in enumerate(requirements):
        if requirement.group_id is None or requirement.group_operator is None:
            continue
        expected = first_operator.setdefault(requirement.group_id, requirement.group_operator)
        if requirement.group_operator != expected:
            conflicts.append(index)
    return conflicts
