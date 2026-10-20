"""48개 전체 판정, AND/OR 진리표, 입력 구조, 기준일 변경을 검증한다."""

from itertools import product
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.contracts.profile import ProfileContent
from app.contracts.requirement import Requirement
from app.modules.eligibility.evaluator import evaluate
from test_eligibility_rules import DATA, POSTINGS, condition, profile, profile_data

STATUSES = ("satisfied", "not_satisfied", "unknown")


def requirement_with_status(status, **updates):
    if status == "unknown":
        return condition("other", None, None, clarity="needs_review", **updates)
    return condition("hours_per_week", "gte", 30 if status == "satisfied" else 31, **updates)


@pytest.mark.parametrize("case", DATA["cases"], ids=lambda case: f"{case['persona']}-{case['posting']}")
def test_all_48_overall_decisions_match_evaluation_data(case):
    content = ProfileContent.model_validate(profile_data(case["persona"]))
    requirements = [Requirement.model_validate(raw) for raw in POSTINGS[case["posting"]]["requirements"]]
    result = evaluate(content, requirements)
    assert result.overall == case["overall"]
    assert not result.structural_issues
    assert not result.no_requirements


@pytest.mark.parametrize("operator,left,right", list(product(("and", "or"), STATUSES, STATUSES)))
def test_all_group_truth_table_combinations(operator, left, right):
    group = str(uuid4())
    requirements = [requirement_with_status(status, group_id=group, group_operator=operator) for status in (left, right)]
    result = evaluate(profile(hours_per_week=30), requirements)
    if operator == "and":
        expected = "not_satisfied" if "not_satisfied" in (left, right) else "unknown" if "unknown" in (left, right) else "satisfied"
    else:
        expected = "satisfied" if "satisfied" in (left, right) else "unknown" if "unknown" in (left, right) else "not_satisfied"
    assert result.overall == expected
    assert result.groups[0].status == expected
    assert [item.status for item in result.conditions] == [left, right]


def test_or_failure_does_not_remove_satisfied_candidate_but_independent_failure_does():
    group = str(uuid4())
    requirements = [requirement_with_status(status, group_id=group, group_operator="or") for status in ("not_satisfied", "satisfied")]
    content = profile(hours_per_week=30)
    assert evaluate(content, requirements).overall == "satisfied"
    assert evaluate(content, [*requirements, requirement_with_status("not_satisfied")]).overall == "not_satisfied"


def test_separate_groups_and_independent_conditions_are_anded():
    group_a, group_b = str(uuid4()), str(uuid4())
    requirements = [
        requirement_with_status("satisfied", group_id=group_a, group_operator="or"),
        requirement_with_status("not_satisfied", group_id=group_a, group_operator="or"),
        requirement_with_status("unknown", group_id=group_b, group_operator="and"),
        requirement_with_status("satisfied"),
    ]
    result = evaluate(profile(hours_per_week=30), requirements)
    assert result.overall == "unknown"
    assert [group.status for group in result.groups] == ["satisfied", "unknown"]


def test_conflicting_group_is_unknown_even_if_all_members_match():
    group = str(uuid4())
    requirements = [requirement_with_status("satisfied", group_id=group, group_operator=operator) for operator in ("and", "or")]
    result = evaluate(profile(hours_per_week=30), requirements)
    assert result.overall == "unknown"
    assert result.groups[0].operator is None
    assert result.structural_issues == ("conflicting_group_operator",)


def test_empty_requirements_are_explicit_and_not_unknown():
    result = evaluate(profile(), [])
    assert result.no_requirements
    assert result.overall == "satisfied"
    assert result.conditions == result.groups == ()


def test_duplicate_ids_are_rejected_instead_of_overwriting_a_result():
    required = requirement_with_status("satisfied")
    with pytest.raises(ValueError, match="중복"):
        evaluate(profile(), [required, required])


def test_excessive_conditions_rejected():
    with pytest.raises(ValueError, match="한도"):
        evaluate(profile(), [requirement_with_status("satisfied") for _ in range(31)])


@pytest.mark.parametrize("updates", [
    {"group_operator": "nested"},
    {"children": []},
    {"group_id": str(uuid4()), "group_operator": None},
    {"group_operator": "and"},
])
def test_unsupported_or_incomplete_group_structure_is_not_flattened(updates):
    with pytest.raises(ValidationError):
        condition("hours_per_week", "gte", 30, **updates)


def test_condition_reference_date_changes_age_result_without_cached_decision():
    content = profile(birth_year=1961)
    results = [evaluate(content, [condition("age", "gte", 65, reference_date=day)]).overall for day in (
        "2025-10-14", "2026-10-14", "2027-10-14",
    )]
    assert results == ["not_satisfied", "unknown", "satisfied"]


def test_profile_change_recomputes_without_mutating_previous_result():
    requirements = [condition("hours_per_week", "gte", 30)]
    first = evaluate(profile(hours_per_week=30), requirements)
    second = evaluate(profile(hours_per_week=20), requirements)
    assert first.overall == "satisfied"
    assert second.overall == "not_satisfied"
