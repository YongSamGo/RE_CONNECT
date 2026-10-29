"""검증된 프로필과 조건의 순수 비교 (W08-01, Plan/02 §4, Plan/04 F07).

확정본·소유권·공고 검수 상태는 호출 서비스가 확인한다. 이 모듈의 결과는 인가나
신청 성공을 보장하지 않는다. 입력·결과를 기록하거나 외부 추론에 보내지 않는다.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.contracts.profile import ProfileContent
from app.contracts.regions import Region
from app.contracts.requirement import Requirement

Status = Literal["satisfied", "not_satisfied", "unknown"]
Reason = Literal[
    "matched", "not_matched", "missing_value", "needs_review",
    "name_equivalence_unverified", "district_unconfirmed", "missing_reference_date",
    "age_boundary", "invalid_birth_year",
]

# 등급을 제거한 같은 종목은 동등하다고 추정하지 않는다. 정확히 같은 이름만 충족이다.
_GRADE = re.compile(r"(?:\s*[1-3]급|기능사|산업기사|기사|기능장|기술사)$")


@dataclass(frozen=True)
class ConditionResult:
    requirement_id: UUID
    status: Status
    reason: Reason


def all_of(results: Iterable[Status]) -> Status:
    values = tuple(results)
    if "not_satisfied" in values:
        return "not_satisfied"
    return "unknown" if "unknown" in values else "satisfied"


def any_of(results: Iterable[Status]) -> Status:
    values = tuple(results)
    if "satisfied" in values:
        return "satisfied"
    return "unknown" if "unknown" in values else "not_satisfied"


def _name_status(held: list[str], required: str) -> Status:
    if required in held:
        return "satisfied"
    if any(
        required in name or name in required or _GRADE.sub("", name) == _GRADE.sub("", required)
        for name in held
    ):
        return "unknown"
    return "not_satisfied"


def _region_status(actual: Region, allowed: Region) -> Status:
    if actual.province != allowed.province:
        return "not_satisfied"
    if allowed.district is None:
        return "satisfied"
    if actual.district is None:
        return "unknown"
    return "satisfied" if actual.district == allowed.district else "not_satisfied"


def compare_condition(profile: ProfileContent, requirement: Requirement) -> ConditionResult:
    """조건별 판정. 허용 연산·값은 Requirement 계약으로 먼저 검증한다.

    사용자 원문에서 이름 동등성·자격 상하관계를 추론하지 않는다. null은 미확인이고
    빈 배열은 없음 확인이다. 연령은 조건 자체의 기준일과 가능한 나이 범위를 쓴다.
    """
    def result(status: Status, reason: Reason | None = None) -> ConditionResult:
        return ConditionResult(requirement.id, status, reason or (
            "matched" if status == "satisfied" else "not_matched"
        ))

    if requirement.clarity != "clear" or requirement.field == "other":
        return result("unknown", "needs_review")

    field, operator, value = requirement.field, requirement.operator, requirement.value
    if field == "age":
        if profile.birth_year is None:
            return result("unknown", "missing_value")
        if requirement.reference_date is None:
            return result("unknown", "missing_reference_date")
        high = requirement.reference_date.year - profile.birth_year
        if high < 0:
            return result("unknown", "invalid_birth_year")
        # 프로젝트 계약은 생일을 수집하지 않는다. 기준일이 연말이어도 같은 보수적 범위.
        low = max(0, high - 1)
        if operator == "gte":
            fits, misses = low >= value, high < value
        elif operator == "lte":
            fits, misses = high <= value, low > value
        elif operator == "between":
            fits = low >= value[0] and high <= value[1]
            misses = high < value[0] or low > value[1]
        else:
            raise ValueError("검증되지 않은 연령 연산")
        if fits:
            return result("satisfied")
        return result("not_satisfied") if misses else result("unknown", "age_boundary")

    if field == "residence_region":
        actual = profile.residence_region
        if actual is None:
            return result("unknown", "missing_value")
        status = any_of(_region_status(actual, allowed) for allowed in value)
        return result(status, "district_unconfirmed" if status == "unknown" else None)

    if field in ("certification", "completed_course"):
        held = profile.certifications if field == "certification" else profile.completed_courses
        if held is None:
            return result("unknown", "missing_value")
        statuses = [_name_status(held, required) for required in value]
        status = all_of(statuses) if operator == "has_all" else any_of(statuses)
        return result(status, "name_equivalence_unverified" if status == "unknown" else None)

    if field == "weekday":
        if profile.available_weekdays is None:
            return result("unknown", "missing_value")
        available, required = set(profile.available_weekdays), set(value)
        matches = required <= available if operator == "includes_all" else bool(required & available)
        return result("satisfied" if matches else "not_satisfied")

    if field == "hours_per_week":
        if profile.hours_per_week is None:
            return result("unknown", "missing_value")
        matches = profile.hours_per_week >= value if operator == "gte" else profile.hours_per_week <= value
        return result("satisfied" if matches else "not_satisfied")

    raise ValueError("검증되지 않은 조건")
