"""운영자 MFA 요청·응답 계약 (docs/api/openapi.yaml MfaVerify·MfaStatus)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictStr

from app.contracts.fields import CONTRACT_CONFIG
from app.contracts.time import UtcDatetime


class MfaVerify(BaseModel):
    model_config = CONTRACT_CONFIG

    otp: Annotated[StrictStr, Field(pattern=r"^[0-9]{6}$", min_length=6, max_length=6)]


class MfaStatus(BaseModel):
    model_config = CONTRACT_CONFIG

    mfa_verified: Literal[True]
    expires_at: UtcDatetime
