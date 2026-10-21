"""공개 동의 계약. 소유자·승인 시각은 요청에서 받지 않는다."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictStr, field_validator

from app.contracts.fields import CONTRACT_CONFIG
from app.contracts.time import to_utc

ConsentPurpose = Literal["ai_processing", "storage"]
NoticeVersion = Annotated[StrictStr, Field(pattern=r"^[a-z0-9._-]{1,32}$", max_length=32)]


class ConsentCreate(BaseModel):
    model_config = CONTRACT_CONFIG

    purpose: ConsentPurpose
    notice_version: NoticeVersion


class ConsentState(ConsentCreate):
    granted_at: datetime

    @field_validator("granted_at")
    @classmethod
    def aware_timestamp(cls, value: datetime) -> datetime:
        return to_utc(value)
