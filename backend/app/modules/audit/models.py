"""감사 기록 조회 계약 (openapi `listAudit`, `AuditEvent`, `AuditList`).

기록은 최소 메타데이터뿐이다. 개인 본문·OTP·토큰·검수 메모는 없고, 공고 검수 사유는 같은 request_id의
검수 근거(opportunity_reviews)에서 찾는다.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.contracts.fields import CONTRACT_CONFIG
from app.contracts.time import UtcDatetime
from app.persistence.operations import AUDIT_RETENTION

ActorRole = Literal["operator", "user", "system"]
AuditAction = Literal[
    "opportunity.create", "opportunity.update", "opportunity.approve", "opportunity.reject", "opportunity.hide",
    "opportunity.close", "report.update", "mfa.verify", "mfa.fail", "mfa.lock", "role.grant", "role.revoke",
    "access.denied",
]
TargetType = Literal["opportunity", "report", "user"]
AuditResult = Literal["success", "denied", "failed"]
PAGE_SIZE = 20


class AuditSearch(BaseModel):
    """조회 기간은 [from, to) 반열린 구간이고 길이는 보관기간(30일)을 넘지 않는다.

    시간대 없는 시각은 거절한다. 계약에 없는 쿼리(행위자·행위 필터 등)는 422로 돌려준다.
    """

    model_config = CONTRACT_CONFIG
    start: UtcDatetime = Field(alias="from")
    end: UtcDatetime = Field(alias="to")
    page: int = Field(default=1, ge=1, le=2**31 - 1)
    page_size: int = Field(default=PAGE_SIZE, ge=1, le=PAGE_SIZE)

    @field_validator("end")
    @classmethod
    def _range(cls, end, info: ValidationInfo):
        start = info.data.get("start")
        if start is not None and not start < end <= start + AUDIT_RETENTION:
            raise PydanticCustomError("audit_range", "조회 기간은 from보다 뒤이고 30일 이내여야 한다")
        return end


class AuditEventView(BaseModel):
    model_config = CONTRACT_CONFIG
    event_id: UUID
    at: UtcDatetime
    actor_id: UUID | None
    actor_role: ActorRole
    action: AuditAction
    target_type: TargetType | None
    target_id: UUID | None
    result: AuditResult
    request_id: str = Field(pattern=r"^req_[0-9A-Za-z]{10,32}$")


class AuditList(BaseModel):
    model_config = CONTRACT_CONFIG
    items: list[AuditEventView] = Field(max_length=PAGE_SIZE)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=PAGE_SIZE)
    total: int = Field(ge=0)
