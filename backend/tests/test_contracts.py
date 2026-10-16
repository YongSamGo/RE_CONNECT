"""공통 데이터 계약 (app/contracts, W02-04).

정상 입력과 함께, 계약 밖 값(불법 enum·시군구·조건 조합)과 서버 관리 필드 끼워 넣기를 거절하는지 본다.
"""

import copy
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.contracts.opportunity import OpportunityContent
from app.contracts.profile import ProfileContent, ProfileContentInput
from app.contracts.regions import DISTRICTS, REGION_CATALOG, Region
from app.contracts.requirement import ALLOWED_OPERATORS, Requirement
from app.contracts.time import KST, UtcDatetime, kst_date, to_utc
from app.core.errors import to_field_errors

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "eval"

REQ_ID = "76dd0c53-31b4-568b-bd86-9525949729f6"
GROUP_ID = "0b6f1f4e-8c1d-4a55-9a3e-2f1c7b9d0a11"


def field_errors(model: type[BaseModel], data: Any) -> list[tuple[str, str]]:
    """검증 실패를 API 422 본문의 (path, reason)으로 바꿔 돌려준다."""
    with pytest.raises(ValidationError) as caught:
        model.model_validate(data)
    return [(error.path, error.reason) for error in to_field_errors(caught.value.errors())]


# --- 지역 ---------------------------------------------------------------------------------------


def test_catalog_lists_three_provinces_with_unique_slugs() -> None:
    assert [province.id for province in REGION_CATALOG.provinces] == ["seoul", "gyeonggi", "incheon"]
    for province in REGION_CATALOG.provinces:
        ids = [district.id for district in province.districts]
        names = [district.name for district in province.districts]
        assert len(ids) == len(set(ids)), province.id
        assert len(names) == len(set(names)), province.id
    counts = {province: len(districts) for province, districts in DISTRICTS.items()}
    assert counts == {"seoul": 25, "gyeonggi": 31, "incheon": 11}


def test_incheon_uses_districts_after_2026_reorganization() -> None:
    names = {name for _, name in DISTRICTS["incheon"]}
    assert {"제물포구", "영종구", "검단구"} <= names
    assert not {"중구", "동구"} & names


@pytest.mark.parametrize(
    "region",
    [
        {"province": "seoul", "district": "yongsan"},
        {"province": "gyeonggi", "district": "suwon"},
        {"province": "incheon", "district": "geomdan"},
        {"province": "seoul", "district": None},
    ],
)
def test_region_accepts_catalog_values(region: dict[str, Any]) -> None:
    assert Region.model_validate(region).model_dump() == region


@pytest.mark.parametrize(
    ("region", "expected"),
    [
        # 다른 시·도의 시·군·구
        ({"province": "seoul", "district": "suwon"}, [("district", "invalid_value")]),
        # 개편 전 인천 구
        ({"province": "incheon", "district": "dong"}, [("district", "invalid_value")]),
        # 한글 이름은 식별값이 아니다
        ({"province": "seoul", "district": "용산구"}, [("district", "invalid_value")]),
        ({"province": "busan", "district": None}, [("province", "invalid_value")]),
        ({"province": "seoul"}, [("district", "required")]),
        ({"province": "seoul", "district": None, "code": "11170"}, [("code", "unknown_field")]),
        # 경로 조작·스크립트 문자열
        ({"province": "seoul", "district": "../etc"}, [("district", "invalid_value")]),
        ({"province": "seoul", "district": "<script>"}, [("district", "invalid_value")]),
        ({"province": "seoul", "district": 1}, [("district", "invalid_type")]),
    ],
)
def test_region_rejects_values_outside_catalog(region: dict[str, Any], expected: list[tuple[str, str]]) -> None:
    assert field_errors(Region, region) == expected


# --- 시각 ---------------------------------------------------------------------------------------


def test_to_utc_converts_offset_and_rejects_naive_datetime() -> None:
    kst_noon = datetime(2026, 10, 16, 12, 0, tzinfo=KST)
    assert to_utc(kst_noon) == datetime(2026, 10, 16, 3, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        to_utc(datetime(2026, 10, 16, 12, 0))


def test_kst_date_crosses_midnight() -> None:
    # UTC 15:00은 한국 다음 날 0시다.
    assert kst_date(datetime(2026, 10, 15, 14, 59, tzinfo=UTC)) == date(2026, 10, 15)
    assert kst_date(datetime(2026, 10, 15, 15, 0, tzinfo=UTC)) == date(2026, 10, 16)


class _Stamp(BaseModel):
    at: UtcDatetime


def test_utc_datetime_type_normalizes_and_rejects_naive() -> None:
    stamp = _Stamp.model_validate({"at": "2026-10-16T12:00:00+09:00"})
    assert stamp.at == datetime(2026, 10, 16, 3, 0, tzinfo=UTC)
    assert stamp.at.utcoffset() == timedelta(0)
    assert field_errors(_Stamp, {"at": "2026-10-16T12:00:00"}) == [("at", "invalid_value")]


# --- 프로필 -------------------------------------------------------------------------------------


def profile(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": 1,
        "experiences": [
            {
                "id": "3f1c2b9a-6d5e-4f7a-8b9c-0d1e2f3a4b5c",
                "description": "초등학교 담임교사",
                "skill_tags": ["학습 지도"],
                "duration_note": None,
            }
        ],
        "skills": ["학습 지도"],
        "preferred_regions": [{"province": "seoul", "district": "seongdong"}],
        "activity_types": ["volunteering"],
        "paid_preference": None,
        "available_weekdays": None,
        "hours_per_week": None,
        "mobility_note": None,
        "residence_region": None,
        "birth_year": None,
        "certifications": None,
        "completed_courses": None,
        "activity_constraints": None,
    }
    data.update(overrides)
    return data


def test_profile_keeps_null_and_empty_list_apart() -> None:
    parsed = ProfileContent.model_validate(profile(certifications=[], completed_courses=None))
    assert parsed.certifications == []
    assert parsed.completed_courses is None
    assert parsed.missing_for_recommendation() == []


def test_profile_reports_missing_for_recommendation() -> None:
    parsed = ProfileContent.model_validate(profile(experiences=[], activity_types=[]))
    assert parsed.missing_for_recommendation() == ["experiences", "activity_types"]


def test_profile_input_accepts_new_experience_without_id() -> None:
    experience = {"id": None, "description": "방과후 독서 지도", "skill_tags": [], "duration_note": "5년"}
    assert ProfileContentInput.model_validate(profile(experiences=[experience])).experiences[0].id is None
    assert field_errors(ProfileContent, profile(experiences=[experience])) == [("experiences[0].id", "invalid_type")]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"activity_types": ["job"]}, [("activity_types[0]", "invalid_value")]),
        ({"activity_types": ["volunteering", "volunteering"]}, [("activity_types", "invalid_value")]),
        ({"paid_preference": "free"}, [("paid_preference", "invalid_value")]),
        ({"available_weekdays": [0, 8]}, [("available_weekdays[0]", "out_of_range"), ("available_weekdays[1]", "out_of_range")]),
        ({"hours_per_week": "6"}, [("hours_per_week", "invalid_type")]),
        ({"hours_per_week": True}, [("hours_per_week", "invalid_type")]),
        ({"birth_year": 2999}, [("birth_year", "out_of_range")]),
        ({"schema_version": 2}, [("schema_version", "invalid_value")]),
        ({"preferred_regions": [{"province": "seoul", "district": "suwon"}]}, [("preferred_regions[0].district", "invalid_value")]),
        ({"skills": ["x" * 51]}, [("skills[0]", "too_long")]),
    ],
)
def test_profile_rejects_invalid_values(overrides: dict[str, Any], expected: list[tuple[str, str]]) -> None:
    assert field_errors(ProfileContent, profile(**overrides)) == expected


def test_profile_requires_every_key_even_optional_ones() -> None:
    data = profile()
    del data["birth_year"]
    assert field_errors(ProfileContent, data) == [("birth_year", "required")]


@pytest.mark.parametrize("server_field", ["confirmed_at", "version", "owner_id", "user_id"])
def test_profile_rejects_server_managed_fields(server_field: str) -> None:
    # 확정 여부·버전·소유자는 서버가 정한다. 클라이언트·AI가 끼워 넣으면 거절한다.
    assert field_errors(ProfileContent, profile(**{server_field: "x"})) == [(server_field, "unknown_field")]


# --- 자격조건 -----------------------------------------------------------------------------------


def requirement(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": REQ_ID,
        "field": "age",
        "operator": "gte",
        "value": 60,
        "group_id": None,
        "group_operator": None,
        "reference_date": None,
        "source_evidence": "만 60세 이상",
        "clarity": "clear",
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    ("field", "operator", "value"),
    [
        ("age", "gte", 60),
        ("age", "lte", 75),
        ("age", "between", [60, 75]),
        ("residence_region", "in", [{"province": "seoul", "district": None}]),
        ("certification", "has_all", ["요양보호사"]),
        ("completed_course", "has_any", ["안전교육"]),
        ("weekday", "includes_all", [2, 4]),
        ("weekday", "includes_any", [6, 7]),
        ("hours_per_week", "lte", 15.5),
        ("hours_per_week", "gte", 10),
    ],
)
def test_requirement_accepts_allowed_combinations(field: str, operator: str, value: Any) -> None:
    parsed = Requirement.model_validate(requirement(field=field, operator=operator, value=value))
    assert parsed.operator == operator


def test_requirement_allowed_table_covers_every_field() -> None:
    assert set(ALLOWED_OPERATORS) == {
        "age",
        "residence_region",
        "certification",
        "completed_course",
        "weekday",
        "hours_per_week",
        "other",
    }


def test_requirement_keeps_unparsed_condition_as_other() -> None:
    parsed = Requirement.model_validate(
        requirement(field="other", operator=None, value=None, clarity="needs_review", source_evidence="체력이 좋으신 분")
    )
    assert parsed.value is None


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        # 허용표에 없는 연산
        ({"operator": "in"}, [("operator", "invalid_value")]),
        ({"field": "weekday", "operator": "gte", "value": 3}, [("operator", "invalid_value")]),
        ({"operator": "eq"}, [("operator", "invalid_value")]),
        ({"field": "salary"}, [("field", "invalid_value")]),
        # 연산과 맞지 않는 값
        ({"value": "60"}, [("value", "invalid_value")]),
        ({"value": 60.5}, [("value", "invalid_value")]),
        ({"value": True}, [("value", "invalid_value")]),
        ({"operator": "between", "value": [75, 60]}, [("value", "invalid_value")]),
        ({"operator": "between", "value": [60]}, [("value", "invalid_value")]),
        ({"field": "weekday", "operator": "includes_all", "value": [2, 2]}, [("value", "invalid_value")]),
        ({"field": "weekday", "operator": "includes_all", "value": [8]}, [("value", "invalid_value")]),
        ({"field": "certification", "operator": "has_all", "value": []}, [("value", "invalid_value")]),
        ({"field": "hours_per_week", "operator": "lte", "value": 200}, [("value", "invalid_value")]),
        (
            {"field": "residence_region", "operator": "in", "value": [{"province": "seoul", "district": "suwon"}]},
            [("value", "invalid_value")],
        ),
        # 해석 못 한 조건을 other가 아닌 field에 null로 두지 않는다
        ({"operator": None, "value": None, "clarity": "needs_review"}, [("operator", "invalid_value")]),
        ({"value": None}, [("value", "invalid_value")]),
        # other는 연산·값 없이 확인 필요로만 둔다
        ({"field": "other", "operator": None, "value": None, "clarity": "clear"}, [("clarity", "invalid_value")]),
        ({"field": "other", "operator": None, "value": 60, "clarity": "needs_review"}, [("value", "invalid_value")]),
        # 그룹 짝
        ({"group_id": GROUP_ID}, [("group_operator", "required_with")]),
        ({"group_operator": "or"}, [("group_operator", "invalid_value")]),
        ({"source_evidence": ""}, [("source_evidence", "too_short")]),
    ],
)
def test_requirement_rejects_combinations_outside_table(
    overrides: dict[str, Any], expected: list[tuple[str, str]]
) -> None:
    assert field_errors(Requirement, requirement(**overrides)) == expected


# --- 공고 ---------------------------------------------------------------------------------------


def opportunity(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "도서관 어르신 책 읽어주기 봉사",
        "organization_name": "용산구립도서관",
        "activity_type": "volunteering",
        "is_public_job": None,
        "role_tags": ["reading_volunteer"],
        "skill_tags": ["독서 지도"],
        "activity_region": {"province": "seoul", "district": "yongsan"},
        "location_text": None,
        "remote_allowed": False,
        "schedule_text": None,
        "hours_per_week": None,
        "paid": False,
        "compensation_text": None,
        "description_text": None,
        "requirements": [],
        "required_documents": None,
        "application_method": "online",
        "application_instructions": "공식 누리집에서 신청",
        "source_url": "https://www.1365.go.kr/vols/1572247904127/partcptn/timeCptn.do",
        "application_url": "https://www.1365.go.kr/vols/1572247904127/partcptn/timeCptn.do",
        "deadline_date": "2026-10-31",
        "deadline_at": None,
        "recruitment_status": "open",
    }
    data.update(overrides)
    return data


def test_opportunity_accepts_contract_example() -> None:
    parsed = OpportunityContent.model_validate(
        opportunity(deadline_at="2026-10-31T18:00:00+09:00", description_text="가" * 5000)
    )
    assert parsed.deadline_at == datetime(2026, 10, 31, 9, 0, tzinfo=UTC)
    assert parsed.requirements == []


def test_opportunity_accepts_groups_with_same_operator() -> None:
    grouped = [
        requirement(id=REQ_ID, group_id=GROUP_ID, group_operator="or"),
        requirement(
            id="3019b5ee-a15d-5601-8bc6-5c010377020c",
            field="certification",
            operator="has_any",
            value=["요양보호사"],
            group_id=GROUP_ID,
            group_operator="or",
        ),
    ]
    assert len(OpportunityContent.model_validate(opportunity(requirements=grouped)).requirements) == 2


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"description_text": "가" * 5001}, [("description_text", "too_long")]),
        ({"source_url": "http://example.com"}, [("source_url", "invalid_value")]),
        ({"application_url": "javascript:alert(1)"}, [("application_url", "invalid_value")]),
        ({"application_url": "https:// evil"}, [("application_url", "invalid_value")]),
        ({"deadline_at": "2026-10-31T18:00:00"}, [("deadline_at", "invalid_value")]),
        ({"activity_region": {"province": "seoul", "district": "bupyeong"}}, [("activity_region.district", "invalid_value")]),
        ({"role_tags": ["Reading Volunteer"]}, [("role_tags[0]", "invalid_value")]),
        ({"recruitment_status": "maybe"}, [("recruitment_status", "invalid_value")]),
        ({"review_status": "approved"}, [("review_status", "unknown_field")]),
    ],
)
def test_opportunity_rejects_invalid_values(overrides: dict[str, Any], expected: list[tuple[str, str]]) -> None:
    assert field_errors(OpportunityContent, opportunity(**overrides)) == expected


def test_opportunity_rejects_conflicting_group_operators() -> None:
    conflicting = [
        requirement(id=REQ_ID, group_id=GROUP_ID, group_operator="or"),
        requirement(id="3019b5ee-a15d-5601-8bc6-5c010377020c", group_id=GROUP_ID, group_operator="and"),
    ]
    assert field_errors(OpportunityContent, opportunity(requirements=conflicting)) == [("requirements", "invalid_value")]


# --- 평가 데이터가 같은 계약을 따르는지 -------------------------------------------------------------


def eval_personas() -> list[Path]:
    return sorted((EVAL_DIR / "personas").glob("*.json"))


def test_eval_files_exist() -> None:
    # 경로가 바뀌어 아래 검사가 빈 목록으로 통과하는 일을 막는다.
    assert eval_personas()
    assert (EVAL_DIR / "eligibility_cases.json").is_file()


@pytest.mark.parametrize("path", eval_personas(), ids=lambda path: path.stem)
def test_eval_persona_regions_are_in_catalog(path: Path) -> None:
    expected = json.loads(path.read_text(encoding="utf-8"))["expected_profile"]
    for region in expected["preferred_regions"]:
        Region.model_validate(region)
    if expected["residence_region"] is not None:
        Region.model_validate(expected["residence_region"])


def test_eval_persona_profiles_match_profile_contract() -> None:
    for path in eval_personas():
        expected = copy.deepcopy(json.loads(path.read_text(encoding="utf-8"))["expected_profile"])
        # 평가 기대값에는 서버가 부여하는 경험 id가 없다. 새 경험으로 보고 검증한다.
        for experience in expected["experiences"]:
            experience.setdefault("id", None)
        ProfileContentInput.model_validate(expected)


def test_eval_requirements_match_requirement_contract() -> None:
    def walk(node: Any) -> list[dict[str, Any]]:
        if isinstance(node, dict):
            found = list(node["requirements"]) if isinstance(node.get("requirements"), list) else []
            return found + [item for value in node.values() for item in walk(value)]
        if isinstance(node, list):
            return [item for value in node for item in walk(value)]
        return []

    cases = json.loads((EVAL_DIR / "eligibility_cases.json").read_text(encoding="utf-8"))
    requirements = walk(cases)
    assert requirements
    for item in requirements:
        Requirement.model_validate(item)

