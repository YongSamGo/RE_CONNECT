"""공식 신청 준비 안내. OpenAPI `Preparation`의 필드를 그대로 표현한다."""

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, StrictInt

from app.contracts.fields import CONTRACT_CONFIG, text
from app.contracts.opportunity import ApplicationMethod, HttpsUrl, RecruitmentStatus
from app.contracts.time import UtcDatetime


class OpportunityRef(BaseModel):
    model_config = CONTRACT_CONFIG

    id: UUID
    version: Annotated[StrictInt, Field(ge=1)]


class Preparation(BaseModel):
    model_config = CONTRACT_CONFIG

    opportunity: OpportunityRef
    application_method: ApplicationMethod
    application_instructions: text(2000, multiline=True)
    application_url: HttpsUrl
    source_url: HttpsUrl
    # null = 명시 없음, [] = 제출할 서류가 없다고 확인함. 추정 목록으로 채우지 않는다.
    required_documents: Annotated[list[text(200)], Field(max_length=20)] | None
    deadline_date: date | None
    deadline_at: UtcDatetime | None
    recruitment_status: RecruitmentStatus
    change_pending: StrictBool
