"""실제 서비스 비교 규칙을 가상 평가 기대값과 경계 사례로 검증한다."""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.contracts.profile import ProfileContent
from app.contracts.requirement import Requirement
from app.modules.eligibility.rules import compare_condition

EVAL = Path(__file__).resolve().parents[2] / "eval"
DATA = json.loads((EVAL / "eligibility_cases.json").read_text(encoding="utf-8"))
POSTINGS = {posting["id"]: posting for posting in DATA["postings"]}


def profile_data(persona="P01"):
    content = json.loads((EVAL / "personas" / f"{persona}.json").read_text(encoding="utf-8"))["expected_profile"]
    for index, experience in enumerate(content["experiences"]):
        experience["id"] = str(UUID(int=index + 1))
    return content


def profile(**updates):
    return ProfileContent.model_validate(profile_data() | updates)


def condition(field, operator, value, **updates):
    return Requirement.model_validate({
        "id": str(uuid4()), "field": field, "operator": operator, "value": value,
        "group_id": None, "group_operator": None, "reference_date": "2026-10-14",
        "source_evidence": "가상 조건", "clarity": "clear", **updates,
    })


@pytest.mark.parametrize("case", DATA["cases"], ids=lambda case: f"{case['persona']}-{case['posting']}")
def test_each_condition_matches_independent_evaluation_cases(case):
    posting = POSTINGS[case["posting"]]
    labels = {value: label for label, value in posting["labels"].items()}
    content = ProfileContent.model_validate(profile_data(case["persona"]))
    for raw in posting["requirements"]:
        evaluated = compare_condition(content, Requirement.model_validate(raw))
        assert evaluated.status == case["conditions"][labels[raw["id"]]]


@pytest.mark.parametrize("field,operator,value,key", [
    ("certification", "has_all", ["전기기사"], "certifications"),
    ("completed_course", "has_any", ["안전 교육"], "completed_courses"),
    ("weekday", "includes_any", [1], "available_weekdays"),
])
def test_null_and_empty_have_different_meanings(field, operator, value, key):
    required = condition(field, operator, value)
    assert compare_condition(profile(**{key: None}), required).status == "unknown"
    assert compare_condition(profile(**{key: []}), required).status == "not_satisfied"


@pytest.mark.parametrize("held,required,status", [
    (["소방안전관리자 1급"], "소방안전관리자 2급", "unknown"),
    (["전기기사"], "전기기능사", "unknown"),
    (["전기기능사"], "전기기사", "unknown"),
    (["서울시 디지털 안내사 교육"], "디지털 안내사 교육", "unknown"),
    (["전기기사"], "전기기사", "satisfied"),
    (["전기기사"], "조리기능사", "not_satisfied"),
])
def test_names_require_verified_equivalence(held, required, status):
    assert compare_condition(profile(certifications=held), condition("certification", "has_all", [required])).status == status


def test_residence_is_not_preferred_region_and_unknown_district_is_not_a_match():
    allowed = [{"province": "seoul", "district": "seongdong"}]
    required = condition("residence_region", "in", allowed)
    assert compare_condition(profile(residence_region=None, preferred_regions=allowed), required).status == "unknown"
    assert compare_condition(profile(residence_region={"province": "seoul", "district": None}), required).status == "unknown"
    assert compare_condition(profile(residence_region={"province": "gyeonggi", "district": None}), required).status == "not_satisfied"
    assert compare_condition(profile(residence_region=allowed[0]), required).status == "satisfied"


@pytest.mark.parametrize("operator,value,hours,status", [
    ("gte", 30, 30, "satisfied"), ("gte", 30, 29.5, "not_satisfied"),
    ("lte", 30, 30, "satisfied"), ("lte", 30, 30.5, "not_satisfied"),
    ("gte", 0, None, "unknown"), ("gte", 0, 0, "satisfied"),
])
def test_hours_include_boundary_and_zero(operator, value, hours, status):
    assert compare_condition(profile(hours_per_week=hours), condition("hours_per_week", operator, value)).status == status


@pytest.mark.parametrize("operator,value,year,status", [
    ("gte", 65, 1960, "satisfied"), ("gte", 65, 1961, "unknown"),
    ("gte", 65, 1962, "not_satisfied"), ("lte", 64, 1961, "unknown"),
    ("between", [64, 65], 1961, "satisfied"), ("between", [65, 65], 1961, "unknown"),
    ("between", [66, 70], 1961, "not_satisfied"),
])
def test_age_range_does_not_guess_birthday(operator, value, year, status):
    assert compare_condition(profile(birth_year=year), condition("age", operator, value)).status == status


def test_age_requires_reference_date_and_valid_birth_year():
    assert compare_condition(profile(birth_year=1961), condition("age", "gte", 65, reference_date=None)).reason == "missing_reference_date"
    assert compare_condition(profile(birth_year=1961), condition("age", "gte", 65, reference_date="1960-01-01")).reason == "invalid_birth_year"


def test_review_needed_cannot_become_satisfied():
    required = condition("hours_per_week", "gte", 0, clarity="needs_review")
    assert compare_condition(profile(hours_per_week=30), required).status == "unknown"
    assert compare_condition(profile(), condition("other", None, None, clarity="needs_review")).status == "unknown"


@pytest.mark.parametrize("operator,value", [("__import__", 30), ("gte", "30"), ("gte", True), ("between", [1, 2])])
def test_untrusted_operators_and_values_are_rejected(operator, value):
    with pytest.raises(ValidationError):
        condition("hours_per_week", operator, value)


def test_client_cannot_supply_an_eligibility_decision():
    with pytest.raises(ValidationError):
        condition("hours_per_week", "gte", 30, status="satisfied")
