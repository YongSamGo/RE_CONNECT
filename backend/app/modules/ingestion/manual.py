"""공식 자료 수동 등록: 최소 근거와 pending 버전을 같은 트랜잭션에 기록한다."""

import hashlib
import json
import re
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, StrictBool, model_validator
from sqlalchemy import func, insert, select, text as sql_text

from app.contracts.fields import CONTRACT_CONFIG, text
from app.contracts.opportunity import HttpsUrl
from app.contracts.time import UtcDatetime, utc_now
from app.core.business_errors import AppError
from app.modules.opportunities.ingestion import RecordOpportunity
from app.modules.opportunities.lifecycle import MAX_CHECK_DELAY, assess_lifecycle
from app.modules.opportunities.versions import OpportunitySnapshot, snapshot_from_row
from app.persistence.operations import ManualEvidence, OpportunityDocument as D, OpportunityVersion as V, RoleDefinition, Source

MAX_INPUT_BYTES = 65536
MANUAL_SOURCES = {
    "manual_50plus": "https://www.50plus.or.kr",
    "manual_work24": "https://www.work24.go.kr",
    "manual_volunteer": "https://www.1365.go.kr",
}
# 기존 수집기와 별도의 수동 경로다. 허용표 변경은 실제 공식 경로 확인 후 코드 리뷰한다.
PATHS = {
    "www.50plus.or.kr": (r"/(?:appView|in_appView)\.do", {"ANN_NO"}),
    "www.work24.go.kr": (r"/wk/a/b/1500/empDetailAuthView\.do", {"wantedAuthNo", "infoTypeCd", "infoTypeGroup"}),
    "www.1365.go.kr": (r"/vols/P9210/partcptn/timeCptn\.do", {"type", "progrmRegistNo"}),
}
REQUIRED_QUOTES = frozenset({"title", "organization_name", "activity_type", "application_method",
                            "application_instructions", "recruitment_status", "requirements"})
QuoteField = Literal["title", "organization_name", "activity_type", "application_method", "application_instructions",
                     "recruitment_status", "requirements", "activity_region", "deadline_date", "deadline_at",
                     "schedule_text", "paid", "compensation_text", "required_documents", "application_url",
                     "is_public_job", "location_text", "remote_allowed", "hours_per_week", "role_tags", "skill_tags", "description_text"]
_CONTACT = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\d)(?:0\d{1,2}[- .]?\d{3,4}[- .]?\d{4}|\d{6}[- ]?[1-4]\d{6})(?!\d)")


def official_url(value):
    parts = urlsplit(value)
    policy = PATHS.get(parts.hostname)
    if (parts.scheme != "https" or parts.fragment or not value.isascii() or not value.isprintable()
            or policy is None or parts.netloc != parts.hostname or not re.fullmatch(policy[0], parts.path)):
        raise ValueError("공식 상세 경로 필요")
    pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    query = dict(pairs)
    if len(query) != len(pairs) or set(query) != policy[1]:
        raise ValueError("공식 상세 식별자 필요")
    if parts.hostname == "www.50plus.or.kr":
        valid = re.fullmatch(r"[1-9][0-9]{0,11}", query["ANN_NO"])
    elif parts.hostname == "www.1365.go.kr":
        valid = query["type"] == "show" and re.fullmatch(r"[1-9][0-9]{0,11}", query["progrmRegistNo"])
    else:
        valid = (re.fullmatch(r"[A-Z0-9]{1,30}", query["wantedAuthNo"]) and query["infoTypeCd"] == "VALIDATION"
                 and query["infoTypeGroup"] == "tb_workinfoworknet")
    if not valid:
        raise ValueError("공식 상세 식별자 오류")
    # 쿼리 순서만 다른 중복을 같은 주소로 취급한다. 임의 리다이렉트는 따라가지 않는다.
    return parts._replace(query="&".join(f"{k}={query[k]}" for k in sorted(query))).geturl()


class Evidence(BaseModel):
    model_config = CONTRACT_CONFIG
    url: HttpsUrl = Field(repr=False)
    observed_at: UtcDatetime
    quotes: Annotated[dict[QuoteField, text(300, multiline=True)], Field(min_length=7, max_length=25, repr=False)]
    confirmed_official: StrictBool

    @model_validator(mode="after")
    def validate_evidence(self):
        official_url(self.url)
        if self.confirmed_official is not True or not REQUIRED_QUOTES <= self.quotes.keys() or any(_CONTACT.search(v) or "<" in v or ">" in v for v in self.quotes.values()):
            raise ValueError("필수 근거 또는 일반 텍스트 확인 필요")
        return self


class ManualInput(BaseModel):
    model_config = CONTRACT_CONFIG
    source_id: UUID
    manual_target: UUID | None = None
    snapshot: OpportunitySnapshot = Field(repr=False)
    evidence: Evidence = Field(repr=False)

    @model_validator(mode="after")
    def validate_material(self):
        snapshot = self.snapshot
        if official_url(snapshot.source_url) != official_url(self.evidence.url):
            raise ValueError("출처와 근거 불일치")
        official_url(snapshot.application_url)
        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strings(child)

        for field in OpportunitySnapshot.model_fields:
            value = getattr(snapshot, field)
            if field not in {"source_url", "application_url"}:
                if any(_CONTACT.search(v) or "<" in v or ">" in v for v in strings(snapshot.model_dump(mode="json")[field])):
                    raise ValueError("연락처 제외 및 일반 텍스트 확인 필요")
        for field in ("activity_region", "deadline_date", "deadline_at", "schedule_text", "paid", "compensation_text", "required_documents",
                      "is_public_job", "location_text", "remote_allowed", "hours_per_week", "role_tags", "skill_tags", "description_text"):
            value = getattr(snapshot, field)
            if value is not None and value != [] and field not in self.evidence.quotes:
                raise ValueError("입력 필드 근거 필요")
        if official_url(snapshot.application_url) != official_url(snapshot.source_url) and "application_url" not in self.evidence.quotes:
            raise ValueError("별도 접수 주소 근거 필요")
        return self


def read_input(stream):
    """stdin만 읽는다. 크기·깊이를 파싱 전에 제한하며 중복 키/NaN을 거절한다."""
    raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("입력 크기 초과")
    serialized = raw.decode("utf-8")
    depth, quoted, escaped = 0, False, False
    for char in serialized:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 24:
                raise ValueError("입력 깊이 초과")
        elif char in "]}":
            depth -= 1

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("중복 입력 키")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("비표준 JSON 값")

    return ManualInput.model_validate(json.loads(serialized, object_pairs_hook=pairs, parse_constant=constant))


class ManualIntake:
    def __init__(self, transaction, store_factory, *, clock=utc_now):
        self.transaction, self.store_factory, self.clock = transaction, store_factory, clock

    @staticmethod
    def _limits(db):
        if db.get_bind().dialect.name == "postgresql":
            db.execute(sql_text("SET LOCAL statement_timeout = 5000"))
            db.execute(sql_text("SET LOCAL lock_timeout = 1000"))

    def record(self, material):
        # 호출자가 model_construct/model_copy를 써도 저장 전 전체 경계를 다시 검사한다.
        material = ManualInput.model_validate(material.model_dump())
        now = self.clock()
        if not now - MAX_CHECK_DELAY <= material.evidence.observed_at <= now:
            raise AppError("VALIDATION_FAILED")
        with self.transaction() as db:
            self._limits(db)
            source = db.execute(select(Source.__table__).where(Source.id == material.source_id).with_for_update()).mappings().one_or_none()
            if source is None or not source["enabled"] or MANUAL_SOURCES.get(source["code"]) != source["base_url"]:
                raise AppError("VALIDATION_FAILED")
            if urlsplit(material.evidence.url).hostname != urlsplit(source["base_url"]).hostname:
                raise AppError("VALIDATION_FAILED")
            roles = set(material.snapshot.role_tags)
            if roles and set(db.scalars(select(RoleDefinition.id).where(RoleDefinition.id.in_(roles)))) != roles:
                raise AppError("VALIDATION_FAILED")
            result = self.store_factory(db).record(RecordOpportunity(source_id=material.source_id, external_id=None,
                snapshot=material.snapshot, checked_at=material.evidence.observed_at, manual_target=material.manual_target))
            if result.outcome == "stale":
                raise AppError("VERSION_CONFLICT")
            evidence = material.evidence.model_dump(mode="json")
            canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            exists = db.scalar(select(ManualEvidence.id).where(ManualEvidence.opportunity_id == result.opportunity_id,
                ManualEvidence.version == result.version, ManualEvidence.evidence_hash == digest))
            if exists is None:
                db.execute(insert(ManualEvidence), {"id": uuid4(), "opportunity_id": result.opportunity_id,
                    "version": result.version, "evidence_url": official_url(material.evidence.url),
                    "observed_at": material.evidence.observed_at, "recorded_at": now,
                    "quotes": dict(material.evidence.quotes), "evidence_hash": digest})
            return result

    def progress(self):
        """최신 버전만 검사하며 주소/기관·제목·마감 중복은 한 건으로 센다. 승인과 후보는 합산하지 않는다."""
        now = self.clock()
        counts = {"target": 20, "recorded_documents": 0, "current_candidates": 0, "current_approved": 0, "held_or_duplicate": 0}
        latest = select(V.opportunity_id, func.max(V.version).label("version")).group_by(V.opportunity_id).subquery()
        evidence = select(ManualEvidence.opportunity_id, ManualEvidence.version,
            func.max(ManualEvidence.observed_at).label("evidence_at")).group_by(ManualEvidence.opportunity_id, ManualEvidence.version).subquery()
        stmt = select(V.__table__, evidence.c.evidence_at, Source.code, Source.base_url).join(latest,
            (latest.c.opportunity_id == V.opportunity_id) & (latest.c.version == V.version)).join(D, D.id == V.opportunity_id
            ).join(Source, Source.id == D.source_id).join(evidence,
            (evidence.c.opportunity_id == V.opportunity_id) & (evidence.c.version == V.version)
            ).where(Source.code.in_(MANUAL_SOURCES), Source.enabled.is_(True)).order_by(V.review_status, V.opportunity_id)
        seen_urls, seen_facts = set(), set()
        with self.transaction() as db:
            self._limits(db)
            for row in db.execute(stmt).mappings():
                counts["recorded_documents"] += 1
                snapshot = snapshot_from_row(row)
                lifecycle = assess_lifecycle(snapshot, source_checked_at=row["evidence_at"], now=now)
                eligible = lifecycle.recommendation_allowed and row["review_status"] in {"pending", "approved"}
                eligible = eligible and MANUAL_SOURCES.get(row["code"]) == row["base_url"]
                eligible = eligible and (snapshot.activity_region is not None or snapshot.remote_allowed is True)
                eligible = eligible and not snapshot.description_truncated and all(r.clarity == "clear" for r in snapshot.requirements)
                key = (snapshot.organization_name.strip().casefold(), snapshot.title.strip().casefold(), snapshot.deadline_date, snapshot.deadline_at)
                url = official_url(snapshot.source_url)
                if not eligible or key in seen_facts or url in seen_urls:
                    counts["held_or_duplicate"] += 1
                    continue
                seen_urls.add(url)
                seen_facts.add(key)
                counts["current_candidates"] += 1
                if row["review_status"] == "approved":
                    counts["current_approved"] += 1
        counts["candidate_shortfall"] = max(0, counts["target"] - counts["current_candidates"])
        counts["approved_shortfall"] = max(0, counts["target"] - counts["current_approved"])
        return counts
