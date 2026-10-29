"""확인된 출처 필드만 OpportunityContent 검수 후보로 옮기는 순수 함수 (#46)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
import re
from typing import Literal
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from pydantic import TypeAdapter, ValidationError

from app.contracts.opportunity import OpportunityContent
from app.contracts.regions import DISTRICTS, Region
from app.contracts.requirement import Requirement
from app.contracts.time import UtcDatetime, kst_date
from app.modules.ingestion.volunteer_regions import VERIFIED_REGIONS


# 수집 공고마다 넣는 "필수조건 미검수" 표식 조건의 근거 첫머리. 운영자가 원문을 읽고 조건을 구조화하거나
# "명시된 필수조건 없음"을 확인해 이 조건을 지우기 전에는 승인하지 않는다(W07-03).
UNREVIEWED_EVIDENCE_PREFIX = "정규화 상태:"
_TIME = TypeAdapter(UtcDatetime)
_ID = re.compile(r"[A-Z0-9]{1,30}")
_VOLUNTEER_ID = re.compile(r"[0-9]{1,12}")
_EMAIL = re.compile(r"[\w.+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}")
_PHONE = re.compile(r"(?<!\d)(?:0\d{1,2}[-. ]?\d{3,4}[-. ]?\d{4}|1[568]\d{2}[-. ]?\d{4})(?!\d)")
_IDENTIFIER = re.compile(r"(?<!\d)\d{6}[- ]?[1-8]\d{6}(?!\d)")
_METHODS = {"방문": "visit", "온라인": "online", "전화": "phone", "이메일": "email"}
_PROVINCES = {"서울": "seoul", "서울특별시": "seoul", "경기": "gyeonggi", "경기도": "gyeonggi",
              "인천": "incheon", "인천광역시": "incheon"}
_OUTSIDE = frozenset({"부산", "부산광역시", "대구", "대구광역시", "대전", "대전광역시", "광주", "광주광역시",
    "울산", "울산광역시", "세종", "세종특별자치시", "강원", "강원특별자치도", "충북", "충청북도", "충남", "충청남도",
    "전북", "전북특별자치도", "전남", "전라남도", "경북", "경상북도", "경남", "경상남도", "제주", "제주특별자치도"})


class _Hold(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    external_id: str
    content: OpportunityContent = field(repr=False)
    description_truncated: bool
    source_checked_at: datetime
    review_reasons: tuple[str, ...]
    unmapped_fields: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    review_status: Literal["pending"] = field(default="pending", init=False)


@dataclass(frozen=True)
class NormalizationResult:
    status: Literal["candidate", "held", "excluded"]
    reason: str | None = None
    candidate: Candidate | None = field(default=None, repr=False)


class _PlainHTML(HTMLParser):
    """속성·URL을 읽지 않고 실행 요소의 내용도 버린다. 네트워크 처리는 없다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag == "embed":
            return  # HTML void 요소이므로 뒤의 일반 본문까지 숨기지 않는다.
        if tag in {"script", "style", "template", "iframe", "object"}:
            self.hidden.append(tag)
        elif not self.hidden and tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()
        elif not self.hidden and tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _value(data: Mapping, name: str) -> str | None:
    value = data.get(name)
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 65536:
        raise _Hold("invalid_source_value")
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    if any(unicodedata.category(c) in {"Cc", "Cf", "Co", "Cs", "Zl", "Zp"} and c not in "\n\t" for c in value):
        raise _Hold("hidden_characters")
    return value.strip() or None


def _scrub(value: str, reasons: set[str]) -> str:
    cleaned = _IDENTIFIER.sub("[식별정보 제외]", value)
    cleaned = _EMAIL.sub("[연락처 제외]", cleaned)
    cleaned = _PHONE.sub("[연락처 제외]", cleaned)
    if cleaned != value:
        reasons.add("contact_redacted")
    return cleaned


def _required_text(value: str, reasons: set[str]) -> str:
    cleaned = _scrub(value, reasons)
    if not cleaned.replace("[식별정보 제외]", "").replace("[연락처 제외]", "").strip():
        raise _Hold("required_field_missing")
    return cleaned


def _unmapped(listing: Mapping, detail: Mapping, reasons: set[str]) -> tuple[tuple[str, str], ...]:
    result = []
    # 검수에 필요한 코드만 보존한다. 원문 전체나 담당자/주소 필드를 복제하지 않는다.
    for name in ("sidoCd", "gugunCd", "actWkdy", "acptMthdCd", "emplymShp", "emplymShpNm", "srvcClCode"):
        value = _value(detail, name) or _value(listing, name)
        if value is not None:
            if len(value) > 64:
                raise _Hold("mapping_value_too_long")
            result.append((name, _scrub(value, reasons)))
    return tuple(result)


def _date(value: str | None) -> date | None:
    if value is None:
        return None
    if re.fullmatch(r"[0-9]{8}", value) is None:
        raise _Hold("invalid_date")
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        raise _Hold("invalid_date") from None


def _region(place: str | None, reasons: set[str]) -> Region | None:
    tokens = (place or "").split()
    if tokens and tokens[0] in _OUTSIDE:
        raise _Hold("outside_region")
    if len(tokens) >= 2 and tokens[0] in _PROVINCES:
        province = _PROVINCES[tokens[0]]
        district = next((slug for slug, name in DISTRICTS[province] if name == tokens[1]), None)
        if district is not None:
            return Region(province=province, district=district)
    reasons.add("region_mapping_unknown")
    return None


def _volunteer_region(listing: Mapping, detail: Mapping, reasons: set[str]) -> Region | None:
    codes = []
    for name in ("sidoCd", "gugunCd"):
        listed, detailed = _value(listing, name), _value(detail, name)
        if listed is not None and detailed is not None and listed != detailed:
            reasons.update({"region_mapping_unknown", "region_mapping_conflict"})
            return None
        codes.append(detailed or listed)
    mapped = VERIFIED_REGIONS.get(tuple(codes))
    if mapped is None:
        reasons.add("region_mapping_unknown")
        return None
    province, district = mapped
    return Region(province=province, district=district)


def _requirement(external_id: str, key: str, evidence: str, *, group=None, op=None, field_name="other", value=None):
    return Requirement(id=uuid5(NAMESPACE_URL, external_id + ":" + key), field=field_name,
        operator=op, value=value, group_id=group[0] if group else None,
        group_operator=group[1] if group else None, reference_date=None,
        source_evidence=evidence, clarity="needs_review")


def _age_requirements(identity: str, age: str, reasons: set[str]) -> list[Requirement]:
    evidence = _scrub("구인 연령: " + age, reasons)
    # 단위/연산이 명시된 원문만 구조화한다. 숫자 '60'을 '만60세 이상'으로 해석하지 않는다.
    join = "or" if " 또는 " in age and " 그리고 " not in age else "and"
    parts = age.split(" 또는 " if join == "or" else " 그리고 ")
    matches = [re.fullmatch(r"만\s*([0-9]{1,3})세\s*(이상|이하)", p) for p in parts]
    if len(parts) <= 10 and all(m is not None and int(m[1]) <= 150 for m in matches):
        group = (uuid5(NAMESPACE_URL, identity + ":age_group"), join) if len(parts) > 1 else None
        return [_requirement(identity, "age_" + str(i), evidence, group=group,
                    op="gte" if m[2] == "이상" else "lte", field_name="age", value=int(m[1]))
                for i, m in enumerate(matches)]
    return [_requirement(identity, "age", evidence)]


def _description(value: str | None, reasons: set[str]) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    parser = _PlainHTML()
    parser.feed(value)
    parser.close()
    text = "".join(parser.parts).strip()
    text = _scrub(text, reasons)
    # 문자 참조로 새로 생긴 제어 문자도 원문 문자와 동일하게 검사한다.
    text = _value({"value": text}, "value")
    if text is None:
        return None, False
    truncated = len(text) > 5000
    if truncated:
        reasons.add("description_truncated")
    return text[:5000], truncated


def _schedule(detail: Mapping, reasons: set[str]) -> str | None:
    start = _value(detail, "actBeginTm")
    end = _value(detail, "actEndTm")
    if start is None and end is None:
        return None
    if (start is None or end is None or re.fullmatch(r"[0-9]{1,2}", start) is None
            or re.fullmatch(r"[0-9]{1,2}", end) is None or not 0 <= int(start) < int(end) <= 24):
        reasons.add("schedule_mapping_unknown")
        return None
    begin = _date(_value(detail, "progrmBgnde"))
    finish = _date(_value(detail, "progrmEndde"))
    if begin and finish and begin > finish:
        raise _Hold("invalid_date_range")
    suffix = f" ({begin.isoformat()} ~ {finish.isoformat()})" if begin and finish else ""
    return f"{int(start)}~{int(end)}시" + suffix


def normalize(source: str, listing: Mapping, detail: Mapping, *, checked_at: datetime) -> NormalizationResult:
    """수집한 목록 1건+상세 1건 → pending 후보. DB·네트워크·LLM 호출과 원문 로깅 없음."""
    reasons = {"requirements_not_reviewed"}
    try:
        if source not in {"senuri", "volunteer"}:
            raise _Hold("unsupported_source")
        checked_at = _TIME.validate_python(checked_at)
        if not isinstance(listing, Mapping) or not isinstance(detail, Mapping) or len(listing) > 128 or len(detail) > 128:
            raise _Hold("invalid_source_value")
        if not detail:
            raise _Hold("detail_missing")
        id_field = "jobId" if source == "senuri" else "progrmRegistNo"
        external_id = _value(listing, id_field)
        matcher = _ID if source == "senuri" else _VOLUNTEER_ID
        if external_id is None or matcher.fullmatch(external_id) is None:
            raise _Hold("invalid_identifier")
        detail_id = _value(detail, id_field)
        if detail_id is not None and detail_id != external_id:
            raise _Hold("identifier_mismatch")
        identity = "reconnect:" + source + ":" + external_id
        today = kst_date(checked_at)
        requirements = []
        if source == "senuri":
            title = _value(detail, "wantedTitle") or _value(listing, "recrtTitle")
            organization = _value(detail, "plbizNm") or _value(listing, "oranNm")
            place = _value(listing, "workPlcNm")
            region = _region(place, reasons)
            if _value(listing, "stmNm") != "워크넷":
                raise _Hold("official_link_unknown")
            auth = _value(detail, "wantedAuthNo")
            if auth is None or _ID.fullmatch(auth) is None:
                raise _Hold("invalid_identifier")
            url = "https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?wantedAuthNo=" + auth + "&infoTypeCd=VALIDATION&infoTypeGroup=tb_workinfoworknet"
            method_raw = _value(listing, "acptMthd")
            methods = (method_raw or "").split(",")
            if not methods or any(m.strip() not in _METHODS for m in methods):
                raise _Hold("application_method_unknown")
            converted = {_METHODS[m.strip()] for m in methods}
            method = next(iter(converted)) if len(converted) == 1 else "mixed"
            deadline = _date(_value(detail, "toAcptDd") or _value(listing, "toDd"))
            begin = _date(_value(detail, "frAcptDd") or _value(listing, "frDd"))
            state = "open" if _value(listing, "deadline") == "접수중" and deadline and (begin is None or begin <= today) else "unknown"
            if deadline is None:
                state = "unknown"
            description, truncated, schedule = None, False, None
            age = _value(detail, "age")
            if age:
                requirements.extend(_age_requirements(identity, age, reasons))
            activity, paid, public_job = "employment", True, None
            instructions = "공식 고용24 상세 페이지에서 접수 방법과 기간을 확인해 주세요."
        else:
            adult = _value(detail, "adultPosblAt")
            if adult == "N":
                raise _Hold("not_senior_target")
            if adult != "Y":
                reasons.add("senior_target_unknown")
            title = _value(detail, "progrmSj") or _value(listing, "progrmSj")
            organization = _value(detail, "mnnstNm")
            reasons.add("organization_mapping_not_reviewed")
            # 표본에서 검수한 코드 쌍만 변환한다. 미등록/상충 코드·인천 개편 전 코드는 보류한다.
            region = _volunteer_region(listing, detail, reasons)
            place = _value(detail, "actPlace")
            url = "https://www.1365.go.kr/vols/P9210/partcptn/timeCptn.do?type=show&progrmRegistNo=" + external_id
            method = "online"
            deadline = _date(_value(detail, "noticeEndde"))
            begin = _date(_value(detail, "noticeBgnde"))
            code = _value(detail, "progrmSttusSe")
            state = "closed" if code == "3" else ("open" if code == "2" and begin and deadline and begin <= today <= deadline else "unknown")
            description, truncated = _description(_value(detail, "progrmCn"), reasons)
            schedule = _schedule(detail, reasons)
            weekday = _value(detail, "actWkdy")
            if weekday:
                requirements.append(_requirement(identity, "weekday", "활동요일 코드: " + _scrub(weekday, reasons)))
                reasons.add("weekday_mapping_unknown")
            activity, paid, public_job = "volunteering", False, False
            instructions = "1365 자원봉사 포털의 공식 상세 페이지에서 모집기간과 신청 절차를 확인해 주세요."
        if begin and deadline and begin > deadline:
            raise _Hold("invalid_date_range")
        if deadline and deadline < today:
            state = "closed"
        # 조건 필드가 없다는 사실을 '필수조건 없음'으로 바꾸지 않는다.
        evidence = UNREVIEWED_EVIDENCE_PREFIX + " 출처의 필수조건 전체 해석·검수가 완료되지 않았습니다."
        if description:
            evidence += "\n미해석 공식 설명(최대 900자): " + description[:900]
        requirements.append(_requirement(identity, "unreviewed", evidence))
        if title is None or organization is None:
            raise _Hold("required_field_missing")
        content = OpportunityContent(title=_required_text(title, reasons), organization_name=_required_text(organization, reasons),
            activity_type=activity, is_public_job=public_job, role_tags=[], skill_tags=[], activity_region=region,
            location_text=_scrub(place, reasons) if place else None, remote_allowed=None, schedule_text=schedule,
            hours_per_week=None, paid=paid, compensation_text=None, description_text=description,
            requirements=requirements, required_documents=None, application_method=method,
            application_instructions=instructions, source_url=url, application_url=url,
            deadline_date=deadline, deadline_at=None, recruitment_status=state)
        unmapped = _unmapped(listing, detail, reasons)
        return NormalizationResult("candidate", candidate=Candidate(external_id, content, truncated,
            checked_at, tuple(sorted(reasons)), unmapped))
    except _Hold as exc:
        code = exc.args[0]
        return NormalizationResult("excluded" if code in {"outside_region", "not_senior_target"} else "held", code)
    except (ValidationError, ValueError, TypeError):
        return NormalizationResult("held", "invalid_contract")


def _item_fields(item) -> dict[str, str | None]:
    """#45에서 안전하게 파싱한 item 하나. 중복/중첩 필드를 dict로 덮어쓰지 않는다."""
    if item is None or item.tag != "item" or item.attrib or len(item) > 128 or (item.text or "").strip():
        raise _Hold("invalid_item_structure")
    values = {}
    for child in item:
        if (re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", child.tag) is None or child.tag in values
                or len(child) or child.attrib or (child.tail or "").strip()):
            raise _Hold("invalid_item_structure")
        values[child.tag] = child.text
    return values


def normalize_items(source: str, listing_item, detail_item, *, checked_at: datetime) -> NormalizationResult:
    """안전 파싱한 목록/상세 item → 중복 검사 → normalize. XML 파싱·HTTP를 다시 하지 않는다."""
    try:
        return normalize(source, _item_fields(listing_item), _item_fields(detail_item), checked_at=checked_at)
    except _Hold as exc:
        return NormalizationResult("held", exc.args[0])
    except (AttributeError, TypeError):
        return NormalizationResult("held", "invalid_item_structure")
