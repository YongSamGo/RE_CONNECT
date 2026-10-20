"""독립 조건과 AND/OR 그룹의 3상태 결합 (W08-02).

미해석 구조를 임의로 평탄화하지 않는다. 이 결과를 HTTP 응답에 연결하는 서비스는
확정·소유권·프로필/공고 버전을 별도로 확인해야 한다(#60).
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.contracts.profile import ProfileContent
from app.contracts.requirement import GroupOperator, Requirement
from app.modules.eligibility.rules import ConditionResult, Status, all_of, any_of, compare_condition


@dataclass(frozen=True)
class GroupResult:
    group_id: UUID
    operator: GroupOperator | None
    status: Status


@dataclass(frozen=True)
class Evaluation:
    overall: Status
    no_requirements: bool
    conditions: tuple[ConditionResult, ...]
    groups: tuple[GroupResult, ...]
    structural_issues: tuple[Literal["conflicting_group_operator"], ...]


def evaluate(profile: ProfileContent, requirements: list[Requirement]) -> Evaluation:
    """그룹을 먼저 평가한 뒤 독립 조건 및 각 그룹 결과를 AND로 결합한다.

    공고 계약이 허용하는 평면 그룹만 받는다. 중첩·알 수 없는 연산은 Requirement
    입력 검증에서 거절한다. 같은 그룹의 연산자가 충돌하면 해당 그룹은 unknown이다.
    중복 조건 ID는 조건별 결과를 덮어쓸 위험이 있으므로 거절한다.
    """
    if len(requirements) > 30:
        raise ValueError("조건 개수 한도 초과")
    if len({item.id for item in requirements}) != len(requirements):
        raise ValueError("중복된 조건 식별자")

    conditions = tuple(compare_condition(profile, item) for item in requirements)
    independent: list[Status] = []
    grouped: dict[UUID, list[tuple[GroupOperator, Status]]] = {}
    for item, result in zip(requirements, conditions, strict=True):
        if item.group_id is None:
            independent.append(result.status)
        else:
            # Requirement 검증은 group_id/연산자가 함께 존재함을 보장한다.
            if item.group_operator is None:
                raise ValueError("검증되지 않은 그룹")
            grouped.setdefault(item.group_id, []).append((item.group_operator, result.status))

    groups: list[GroupResult] = []
    issues: list[Literal["conflicting_group_operator"]] = []
    for group_id, members in grouped.items():
        operators = {operator for operator, _ in members}
        if len(operators) != 1:
            groups.append(GroupResult(group_id, None, "unknown"))
            if "conflicting_group_operator" not in issues:
                issues.append("conflicting_group_operator")
            continue
        operator = members[0][0]
        statuses = [status for _, status in members]
        status = all_of(statuses) if operator == "and" else any_of(statuses)
        groups.append(GroupResult(group_id, operator, status))

    return Evaluation(
        overall=all_of([*independent, *(group.status for group in groups)]),
        no_requirements=not requirements,
        conditions=conditions,
        groups=tuple(groups),
        structural_issues=tuple(issues),
    )
