"""가상 출처 표본으로 사실 보존·조건 그룹·정규화 공격 경계를 검사한다."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
import json
import xml.etree.ElementTree as ET

import pytest

from app.modules.ingestion.normalize import normalize, normalize_items


NOW = datetime(2026, 10, 20, 3, tzinfo=UTC)


@pytest.fixture
def job():
    return ({"jobId": "FIXTURE1", "recrtTitle": "가상 도서 정리", "oranNm": "가상기관",
             "workPlcNm": "경기 안양시 동안구", "stmNm": "워크넷", "acptMthd": "방문",
             "frDd": "20261001", "toDd": "20261031", "deadline": "접수중"},
            {"wantedTitle": "가상 도서 정리 상세", "plbizNm": "가상 상세기관",
             "wantedAuthNo": "KFIXTURE1", "age": "60"})


@pytest.fixture
def volunteer():
    return ({"progrmRegistNo": "123", "progrmSj": "가상 안내 봉사", "sidoCd": "6110000"},
            {"progrmRegistNo": "123", "progrmSj": "가상 안내 봉사", "mnnstNm": "가상기관",
             "adultPosblAt": "Y", "noticeBgnde": "20261001", "noticeEndde": "20261031",
             "progrmSttusSe": "2", "actPlace": "가상 활동센터", "actBeginTm": "14", "actEndTm": "16",
             "progrmBgnde": "20261021", "progrmEndde": "20261031", "actWkdy": "0001000",
             "progrmCn": "<p>공식 원문을 가정한 <b>가상 시험</b>입니다.</p>"})


def call(source, sample, **kwargs):
    return normalize(source, *sample, checked_at=kwargs.pop("checked_at", NOW), **kwargs)


@pytest.mark.parametrize("codes,expected", [
    (("6110000", "3030000"), ("seoul", "seongdong")),
    (("6410000", "3780000"), ("gyeonggi", "seongnam")),
    (("6280000", "3520000"), ("incheon", "yeonsu")),
])
def test_reviewed_volunteer_code_pairs_resolve_without_address(volunteer, codes, expected):
    volunteer[0].update(zip(("sidoCd", "gugunCd"), codes))
    candidate = call("volunteer", volunteer).candidate
    assert (candidate.content.activity_region.province, candidate.content.activity_region.district) == expected
    assert "region_mapping_unknown" not in candidate.review_reasons
    assert candidate.review_status == "pending"
    assert candidate.content.skill_tags == candidate.content.role_tags == []
    assert "requirements_not_reviewed" in candidate.review_reasons
    assert dict(candidate.unmapped_fields)["gugunCd"] == codes[1]


def test_volunteer_detail_only_codes_are_supported(volunteer):
    volunteer[0].pop("sidoCd")
    volunteer[1].update(sidoCd="6110000", gugunCd="3030000")
    assert call("volunteer", volunteer).candidate.content.activity_region.district == "seongdong"


@pytest.mark.parametrize("codes", [
    ("6110000", "3520000"), ("6280000", "3030000"),  # 시도/시군구 불일치
    ("6280000", "3490000"), ("6280000", "3500000"), ("6280000", "3560000"),  # 인천 개편 전
    ("6110000", None), (None, "3030000"), ("6110000", "9999999"),
    ("6110000", "3030000; arbitrary"),
])
def test_unknown_or_ambiguous_volunteer_codes_never_broaden_region(volunteer, codes):
    volunteer[0].update(zip(("sidoCd", "gugunCd"), codes))
    volunteer[1]["actPlace"] = "서울 성동구 가상센터"  # 미확인 코드를 주소 추정으로 우회하지 않는다.
    result = call("volunteer", volunteer)
    assert result.status == "candidate"
    assert result.candidate.content.activity_region is None
    assert "region_mapping_unknown" in result.candidate.review_reasons


@pytest.mark.parametrize("field,value", [("sidoCd", "6410000"), ("gugunCd", "3040000")])
def test_conflicting_volunteer_list_detail_codes_require_review(volunteer, field, value):
    volunteer[0].update(sidoCd="6110000", gugunCd="3030000")
    volunteer[1][field] = value
    candidate = call("volunteer", volunteer).candidate
    assert candidate.content.activity_region is None
    assert {"region_mapping_unknown", "region_mapping_conflict"} <= set(candidate.review_reasons)


def test_job_maps_confirmed_fields_only(job):
    result = call("senuri", job)
    assert result.status == "candidate"
    candidate = result.candidate
    assert candidate.review_status == "pending"
    content = candidate.content
    assert content.title == "가상 도서 정리 상세"
    assert content.organization_name == "가상 상세기관"
    assert content.activity_region.province == "gyeonggi"
    assert content.activity_region.district == "anyang"
    assert content.location_text == "경기 안양시 동안구"
    assert content.description_text is None and candidate.description_truncated is False
    assert content.remote_allowed is None and content.hours_per_week is None
    assert content.compensation_text is None and content.is_public_job is None
    assert content.role_tags == content.skill_tags == []
    assert content.deadline_date.isoformat() == "2026-10-31" and content.deadline_at is None
    assert content.recruitment_status == "open"
    assert content.application_method == "visit"
    assert "wantedAuthNo=KFIXTURE1&infoTypeCd=VALIDATION" in content.application_url
    assert content.source_url == content.application_url


def test_unclear_age_is_not_assumed_to_be_a_minimum(job):
    content = call("senuri", job).candidate.content
    age, pending = content.requirements
    assert age.field == "other" and age.operator is age.value is None
    assert age.source_evidence == "구인 연령: 60"
    assert age.clarity == pending.clarity == "needs_review"


@pytest.mark.parametrize("age,operation", [
    ("만 60세 이상 그리고 만 70세 이하", "and"),
    ("만 60세 이상 또는 만 70세 이하", "or"),
])
def test_explicit_and_or_preserved_and_stable(job, age, operation):
    job[1]["age"] = age
    first = call("senuri", job).candidate.content
    second = call("senuri", job).candidate.content
    conditions = first.requirements[:2]
    assert [r.operator for r in conditions] == ["gte", "lte"]
    assert [r.value for r in conditions] == [60, 70]
    assert conditions[0].group_id == conditions[1].group_id
    assert all(r.group_operator == operation and r.reference_date is None and r.clarity == "needs_review" for r in conditions)
    assert first.model_dump() == second.model_dump()


@pytest.mark.parametrize("age", ["60세 이상", "만 60세 이상 또는 만 70세 이하 그리고 만 80세 이하", "만 999세 이상", "제한 없음"])
def test_unsupported_or_ambiguous_conditions_remain_original_other(job, age):
    job[1]["age"] = age
    result = call("senuri", job)
    assert result.status == "candidate"
    assert result.candidate.content.requirements[0].field == "other"
    assert age in result.candidate.content.requirements[0].source_evidence


def test_absent_conditions_never_mean_verified_no_requirements(job):
    job[1].pop("age")
    content = call("senuri", job).candidate.content
    assert len(content.requirements) == 1
    assert content.requirements[0].field == "other"
    assert content.requirements[0].clarity == "needs_review"


def test_volunteer_preserves_description_without_inventing_weekly_hours(volunteer):
    candidate = call("volunteer", volunteer).candidate
    content = candidate.content
    assert content.activity_type == "volunteering" and content.paid is False and content.is_public_job is False
    assert content.description_text == "공식 원문을 가정한 가상 시험입니다."
    assert content.schedule_text == "14~16시 (2026-10-21 ~ 2026-10-31)"
    assert content.hours_per_week is None and content.activity_region is None
    assert content.application_url.endswith("progrmRegistNo=123")
    assert content.requirements[0].field == "other" and "0001000" in content.requirements[0].source_evidence
    assert {"region_mapping_unknown", "weekday_mapping_unknown"} <= set(candidate.review_reasons)
    assert dict(candidate.unmapped_fields) == {"sidoCd": "6110000", "actWkdy": "0001000"}


def test_organization_does_not_fall_back_to_volunteer_registration_center(volunteer):
    volunteer[1].pop("mnnstNm")
    volunteer[1]["nanmmbyNm"] = "등록센터를 모집기관으로 추정하면 안 됨"
    result = call("volunteer", volunteer)
    assert result.status == "held" and result.reason == "required_field_missing"


def test_html_never_retains_active_content_or_attributes(volunteer):
    volunteer[1]["progrmCn"] = '<p onclick="steal()">공식 설명</p><script>fixture-secret</script><style>hidden</style><iframe src="http://127.0.0.1">hidden</iframe><a href="javascript:steal()">읽을 문구</a>'
    description = call("volunteer", volunteer).candidate.content.description_text
    assert description == "공식 설명\n읽을 문구"
    assert "fixture-secret" not in description and "steal" not in description


def test_hidden_characters_in_html_entity_are_held(volunteer):
    volunteer[1]["progrmCn"] = "본문&#x202e;숨김"
    result = call("volunteer", volunteer)
    assert result.status == "held" and result.reason == "hidden_characters"


def test_void_embed_does_not_swallow_following_visible_description(volunteer):
    volunteer[1]["progrmCn"] = '<embed src="http://127.0.0.1/fixture"><p>남겨야 할 공식 설명</p>'
    assert call("volunteer", volunteer).candidate.content.description_text == "남겨야 할 공식 설명"


def test_contacts_and_unselected_private_fields_do_not_enter_candidate(volunteer):
    # 가상의 연락처/식별정보 형태. 실제 개인정보 아님.
    volunteer[1]["progrmCn"] = "가상 연락처 010-0000-0000, fixture@example.invalid, 000101-1000000"
    volunteer[1].update({"telno": "DROP_ME", "email": "DROP_ME", "nanmmbyNmAdmn": "DROP_ME", "areaAddress1": "DROP_ME"})
    candidate = call("volunteer", volunteer).candidate
    serialized = json.dumps(candidate.content.model_dump(mode="json"), ensure_ascii=False)
    assert all(v not in serialized for v in ("DROP_ME", "010-0000-0000", "fixture@example.invalid", "000101-1000000"))
    assert "contact_redacted" in candidate.review_reasons
    assert "가상" not in repr(candidate) + repr(call("volunteer", volunteer))


@pytest.mark.parametrize("length,truncated", [(4999, False), (5000, False), (5001, True)])
def test_description_cut_and_flag_without_replacement(volunteer, length, truncated):
    volunteer[1]["progrmCn"] = "가" * length
    candidate = call("volunteer", volunteer).candidate
    assert len(candidate.content.description_text) == min(length, 5000)
    assert candidate.description_truncated is truncated
    assert ("description_truncated" in candidate.review_reasons) is truncated


@pytest.mark.parametrize("field,value,reason", [
    ("wantedAuthNo", "https://attacker.invalid", "invalid_identifier"),
    ("wantedAuthNo", "ABC&redirect=evil", "invalid_identifier"),
    ("jobId", "OTHER", "identifier_mismatch"),
    ("wantedTitle", "가" * 201, "invalid_contract"),
    ("wantedTitle", "숨김\u202e", "hidden_characters"),
    ("toAcptDd", "20260230", "invalid_date"),
    ("frAcptDd", "20261101", "invalid_date_range"),
])
def test_bad_source_values_are_held_without_raw_errors(job, field, value, reason):
    job[1][field] = value
    result = call("senuri", job)
    assert result.status == "held" and result.reason == reason
    assert result.candidate is None and value not in repr(result)


def test_external_urls_and_llm_like_authority_fields_are_ignored(job):
    job[1].update({"application_url": "https://attacker.invalid", "source_url": "https://attacker.invalid", "review_status": "approved", "role_tags": "administrator", "id": "OVERRIDE"})
    candidate = call("senuri", job).candidate
    assert candidate.review_status == "pending"
    assert "attacker" not in candidate.content.application_url
    assert candidate.content.role_tags == []


def test_unverified_codes_preserved_without_becoming_roles_or_application_method(job):
    job[0].update({"emplymShp": "CM0105", "acptMthdCd": "UNVERIFIED"})
    candidate = call("senuri", job).candidate
    assert dict(candidate.unmapped_fields) == {"acptMthdCd": "UNVERIFIED", "emplymShp": "CM0105"}
    assert candidate.content.role_tags == [] and candidate.content.application_method == "visit"


def test_source_cannot_override_truncation_or_verification_metadata(volunteer):
    volunteer[1].update({"progrmCn": "가" * 5001, "description_truncated": "false", "review_status": "approved"})
    candidate = call("volunteer", volunteer).candidate
    assert candidate.description_truncated is True and candidate.review_status == "pending"


@pytest.mark.parametrize("place,province,district", [
    ("서울 노원구", "seoul", "nowon"), ("서울특별시 중구", "seoul", "jung"),
    ("경기도 수원시 영통구", "gyeonggi", "suwon"), ("인천광역시 제물포구", "incheon", "jemulpo"),
])
def test_regions_use_current_catalog(job, place, province, district):
    job[0]["workPlcNm"] = place
    region = call("senuri", job).candidate.content.activity_region
    assert (region.province, region.district) == (province, district)


@pytest.mark.parametrize("place", ["전남광주", "인천 중구", "서울 미확인구", "서울"])
def test_unknown_or_old_region_not_broadened_to_whole_province(job, place):
    job[0]["workPlcNm"] = place
    result = call("senuri", job)
    assert result.status == "candidate" and result.candidate.content.activity_region is None
    assert "region_mapping_unknown" in result.candidate.review_reasons


def test_known_outside_region_is_distinct_from_held_unknown_mapping(job):
    job[0]["workPlcNm"] = "부산 해운대구"
    result = call("senuri", job)
    assert (result.status, result.reason) == ("excluded", "outside_region")


def test_adult_n_is_excluded_but_missing_is_unknown(volunteer):
    volunteer[1]["adultPosblAt"] = "N"
    result = call("volunteer", volunteer)
    assert (result.status, result.reason) == ("excluded", "not_senior_target")
    volunteer[1].pop("adultPosblAt")
    result = call("volunteer", volunteer)
    assert result.status == "candidate" and "senior_target_unknown" in result.candidate.review_reasons


@pytest.mark.parametrize("code,end,status", [("2", "20261020", "open"), ("2", "20261019", "closed"), ("3", "20261031", "closed"), ("99", "20261031", "unknown")])
def test_volunteer_status_and_date_precedence(volunteer, code, end, status):
    volunteer[1].update({"progrmSttusSe": code, "noticeEndde": end})
    assert call("volunteer", volunteer).candidate.content.recruitment_status == status


def test_korean_date_used_at_utc_midnight_boundary(job):
    job[0]["toDd"] = "20261020"
    assert call("senuri", job, checked_at=datetime(2026, 10, 20, 14, 59, tzinfo=UTC)).candidate.content.recruitment_status == "open"
    assert call("senuri", job, checked_at=datetime(2026, 10, 20, 15, 0, tzinfo=UTC)).candidate.content.recruitment_status == "closed"


@pytest.mark.parametrize("value", ["FAX", "CM001", "방문 또는 다른 방법"])
def test_unknown_application_method_not_invented(job, value):
    job[0]["acptMthd"] = value
    result = call("senuri", job)
    assert result.status == "held" and result.reason == "application_method_unknown"


def test_no_detail_or_unknown_source_never_creates_candidate(job):
    assert call("senuri", (job[0], {})).reason == "detail_missing"
    assert call("unknown", job).reason == "unsupported_source"
    assert call("senuri", job, checked_at=datetime(2026, 10, 20)).reason == "invalid_contract"


def test_candidate_cannot_accept_approved_flag(job):
    candidate = call("senuri", job).candidate
    with pytest.raises(ValueError):
        replace(candidate, review_status="approved")
    with pytest.raises(FrozenInstanceError):
        candidate.review_status = "approved"


def test_duplicate_application_methods_are_not_invented_as_mixed(job):
    job[0]["acptMthd"] = "방문,방문"
    assert call("senuri", job).candidate.content.application_method == "visit"


def test_required_name_replaced_entirely_by_redaction_is_held(job):
    job[1]["plbizNm"] = "fixture@example.invalid"
    assert call("senuri", job).reason == "required_field_missing"


def test_unparsed_qualification_text_is_preserved_without_inventing_a_predicate(volunteer):
    volunteer[1]["progrmCn"] = "자격 A 또는 자격 B를 갖추어야 합니다."
    result = call("volunteer", volunteer)
    condition = result.candidate.content.requirements[-1]
    assert condition.field == "other" and condition.operator is condition.value is None
    assert volunteer[1]["progrmCn"] in condition.source_evidence


def item(fields):
    root = ET.Element("item")
    for key, value in fields.items():
        ET.SubElement(root, key).text = value
    return root


def test_parsed_items_use_same_normalization_contract(job):
    result = normalize_items("senuri", item(job[0]), item(job[1]), checked_at=NOW)
    assert result == call("senuri", job)


@pytest.mark.parametrize("shape", ["duplicate", "nested", "attributes", "mixed", "missing"])
def test_xml_shape_does_not_hide_ambiguous_or_overwritten_fields(job, shape):
    listing, detail = item(job[0]), item(job[1])
    if shape == "duplicate":
        ET.SubElement(detail, "wantedAuthNo").text = "WRONG"
    elif shape == "nested":
        ET.SubElement(detail[0], "unexpected").text = "nested"
    elif shape == "attributes":
        detail[0].set("href", "http://127.0.0.1")
    elif shape == "mixed":
        detail[0].tail = "unexpected content"
    else:
        detail = None
    result = normalize_items("senuri", listing, detail, checked_at=NOW)
    assert result.status == "held" and result.reason == "invalid_item_structure"
