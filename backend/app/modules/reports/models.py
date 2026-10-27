"""공고 오류 신고 요청·응답 (openapi `ReportCreate`, `ReportReceipt`, `AdminReport*`, `ReportUpdate`).

설명과 처리 사유는 공고 오류를 적는 칸이다. 연락처·주민번호처럼 알려진 개인정보 형식이나 지시문이
보이면 저장하지 않고 422로 돌려준다. 걸러도 남을 수 있는 개인정보에 대비해 저장은 암호화로만 한다.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.contracts.fields import CONTRACT_CONFIG, text
from app.contracts.preparation import OpportunityRef
from app.contracts.time import UtcDatetime
from app.modules.generation.privacy import safe_text

ReportType = Literal["already_closed", "wrong_requirements", "wrong_schedule_or_location", "wrong_application_method", "broken_link", "other"]
ReportStatus = Literal["received", "in_progress", "resolved", "dismissed"]
HandledStatus = Literal["in_progress", "resolved", "dismissed"]
TERMINAL: frozenset[str] = frozenset({"resolved", "dismissed"})
# 처리는 한 방향이다. 종결한 신고는 다시 열지 않는다.
TRANSITIONS: dict[str, frozenset[str]] = {"received": frozenset({"in_progress"}), "in_progress": TERMINAL}
Note = text(500, multiline=True)


def _private(note: str | None) -> str | None:
    if note is not None and safe_text(note) is None:
        raise PydanticCustomError("private_note", "설명에 개인정보나 지시문으로 보이는 내용이 있다")
    return note


class ReportCreate(BaseModel):
    model_config = CONTRACT_CONFIG
    opportunity: OpportunityRef
    type: ReportType
    note: Note | None

    @field_validator("note")
    @classmethod
    def _note(cls, note: str | None, info: ValidationInfo) -> str | None:
        if note is None and info.data.get("type") == "other":
            raise PydanticCustomError("required_with", "그 밖의 오류는 설명이 필요하다")
        return _private(note)


class ReportReceipt(BaseModel):
    model_config = CONTRACT_CONFIG
    report_id: UUID
    received_at: UtcDatetime


class ReportUpdate(BaseModel):
    model_config = CONTRACT_CONFIG
    base_version: Annotated[StrictInt, Field(ge=1, le=2**31 - 2)]
    status: HandledStatus
    resolution_note: Note | None

    @field_validator("resolution_note")
    @classmethod
    def _resolution(cls, note: str | None, info: ValidationInfo) -> str | None:
        if note is None and info.data.get("status") in TERMINAL:
            raise PydanticCustomError("required_with", "종결에는 처리 사유가 필요하다")
        return _private(note)


class AdminReport(BaseModel):
    model_config = CONTRACT_CONFIG
    report_id: UUID
    version: Annotated[StrictInt, Field(ge=1)]
    opportunity: OpportunityRef
    opportunity_title: Annotated[str, Field(max_length=200)]
    type: ReportType
    note: Annotated[str, Field(max_length=500)] | None
    status: ReportStatus
    resolution_note: Annotated[str, Field(max_length=500)] | None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class AdminReportList(BaseModel):
    model_config = CONTRACT_CONFIG
    items: Annotated[list[AdminReport], Field(max_length=20)]
    page: Annotated[StrictInt, Field(ge=1)]
    page_size: Annotated[StrictInt, Field(ge=1, le=20)]
    total: Annotated[StrictInt, Field(ge=0)]
