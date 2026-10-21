"""수집/운영 수정/공개/추천이 공유하는 중요 변경 규칙 (Plan/02 §6)."""

import hashlib
import json
from collections.abc import Mapping

from pydantic import StrictBool

from app.contracts.opportunity import OpportunityContent

IMPORTANT_FIELDS = frozenset({
    "activity_type", "requirements", "activity_region", "remote_allowed", "schedule_text",
    "hours_per_week", "deadline_date", "deadline_at", "application_method", "application_url",
    "application_instructions", "required_documents", "paid", "source_url",
})
IMPORTANT_STATUS_TRANSITIONS = frozenset({("closed", "open"), ("open", "unknown")})


class OpportunitySnapshot(OpportunityContent):
    description_truncated: StrictBool


def snapshot_from_row(row: Mapping) -> OpportunitySnapshot:
    values = {name: row[name] for name in OpportunitySnapshot.model_fields if name != "activity_region"}
    values["activity_region"] = None if row["activity_province"] is None else {"province": row["activity_province"], "district": row["activity_district"]}
    return OpportunitySnapshot.model_validate(values)


def content_hash(snapshot: OpportunitySnapshot) -> str:
    """생성 당시 정규화 콘텐츠 해시. 공개 승인·콘텐츠 진위의 증명이 아니다."""
    serialized = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def changed_fields(before: OpportunitySnapshot, after: OpportunitySnapshot) -> frozenset[str]:
    return frozenset(name for name in OpportunitySnapshot.model_fields if getattr(before, name) != getattr(after, name))


def important_changes(before: OpportunitySnapshot, after: OpportunitySnapshot) -> frozenset[str]:
    changes = changed_fields(before, after) & IMPORTANT_FIELDS
    if (before.recruitment_status, after.recruitment_status) in IMPORTANT_STATUS_TRANSITIONS:
        changes |= {"recruitment_status"}
    return changes
