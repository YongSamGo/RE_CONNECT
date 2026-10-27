"""운영자 검수 요청·응답 (openapi `Opportunity*Request`, `OpportunityReviewResult`).

메모는 개인정보를 적지 않는 공고 확인 내용이다. 연락처·주민번호처럼 알려진 개인정보 형식이나
지시문이 보이면 저장하지 않고 422로 돌려준다.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.contracts.fields import CONTRACT_CONFIG, text
from app.contracts.time import UtcDatetime
from app.modules.generation.privacy import safe_text

Action = Literal["approve", "reject", "hide", "close"]
ReviewStatus = Literal["pending", "approved", "rejected", "hidden"]
RejectReason = Literal["source_unverifiable", "out_of_scope", "recruitment_closed", "duplicate",
                       "insufficient_information", "inappropriate_content", "other"]
CloseBasis = Literal["source_closed", "deadline_passed", "organization_notice", "report_confirmed", "other"]
BaseVersion = Annotated[StrictInt, Field(ge=1)]
Note = text(500, multiline=True)


def _private(note: str | None) -> str | None:
    if note is not None and safe_text(note) is None:
        raise PydanticCustomError("private_note", "메모에 개인정보나 지시문으로 보이는 내용이 있다")
    return note


def _required_for_other(note: str | None, info: ValidationInfo, field: str) -> str | None:
    if note is None and info.data.get(field) == "other":
        raise PydanticCustomError("required_with", "기타를 고르면 메모가 필요하다")
    return _private(note)


class ApproveRequest(BaseModel):
    model_config = CONTRACT_CONFIG
    base_version: BaseVersion
    note: Note

    _note = field_validator("note")(_private)


class HideRequest(ApproveRequest):
    pass


class RejectRequest(BaseModel):
    model_config = CONTRACT_CONFIG
    base_version: BaseVersion
    reason_code: RejectReason
    note: Note | None

    @field_validator("note")
    @classmethod
    def _note(cls, note, info):
        return _required_for_other(note, info, "reason_code")


class CloseRequest(BaseModel):
    model_config = CONTRACT_CONFIG
    base_version: BaseVersion
    basis: CloseBasis
    note: Note | None

    @field_validator("note")
    @classmethod
    def _note(cls, note, info):
        return _required_for_other(note, info, "basis")


class ReviewResult(BaseModel):
    model_config = CONTRACT_CONFIG
    id: UUID
    version: BaseVersion
    review_status: ReviewStatus
    reviewed_at: UtcDatetime


@dataclass(frozen=True)
class ReviewCommand:
    """서버가 정한 주체·시각·요청 ID와 검증한 요청 값. 클라이언트가 고를 수 없는 값만 여기서 붙인다."""

    action: Action
    base_version: int
    reason_code: str | None
    note: str | None
    actor_id: UUID
    request_id: str
    at: datetime
