"""공개 조회 계약. 읽기는 세션·AI·Redis와 무관하게 DB 공개 포인터를 따른다."""

from datetime import date, datetime, UTC
from typing import Annotated, Protocol
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.contracts.fields import CONTRACT_CONFIG, ActivityType, text
from app.contracts.opportunity import OpportunityContent, RecruitmentStatus
from app.contracts.preparation import Preparation, OpportunityRef
from app.contracts.regions import Province, Region, is_known_district
from app.contracts.time import UtcDatetime
from app.core.business_errors import AppError


class OpportunitySearch(BaseModel):
    model_config = CONTRACT_CONFIG
    q: text(100) | None = None
    province: Province | None = None
    district: str | None = Field(default=None, pattern=r"^[a-z0-9_]{2,40}$")
    activity_type: ActivityType | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=20)

    @model_validator(mode="before")
    @classmethod
    def _province_required(cls, values):
        if isinstance(values, dict) and values.get("district") is not None and values.get("province") is None:
            raise ValidationError.from_exception_data("OpportunitySearch", [{"type": PydanticCustomError("required_with", "시·도를 함께 선택해야 합니다"), "loc": ("province",), "input": None}])
        return values

    @field_validator("district")
    @classmethod
    def _district_known(cls, value, info):
        province = info.data.get("province")
        if value is not None and province is not None and not is_known_district(province, value):
            raise PydanticCustomError("unknown_district", "지역 목록에 없는 시·군·구")
        return value


class PublicOpportunity(OpportunityContent):
    id: UUID
    version: int = Field(ge=1)
    description_truncated: bool
    source_checked_at: UtcDatetime
    reviewed_at: UtcDatetime
    change_pending: bool


class OpportunitySummary(BaseModel):
    model_config = CONTRACT_CONFIG
    id: UUID
    version: int
    title: str
    organization_name: str
    activity_type: ActivityType
    is_public_job: bool | None
    activity_region: Region | None
    remote_allowed: bool | None
    paid: bool | None
    deadline_date: date | None
    deadline_at: UtcDatetime | None
    recruitment_status: RecruitmentStatus
    change_pending: bool


class OpportunityPage(BaseModel):
    model_config = CONTRACT_CONFIG
    items: Annotated[list[OpportunitySummary], Field(max_length=20)]
    page: int
    page_size: int
    total: int


class PublicOpportunityRepository(Protocol):
    def list(self, search: OpportunitySearch, now: datetime) -> OpportunityPage: ...
    def get(self, opportunity_id: UUID, now: datetime) -> PublicOpportunity | None: ...


class PublicOpportunityService:
    def __init__(self, repository: PublicOpportunityRepository):
        self.repository = repository

    def list(self, search: OpportunitySearch) -> OpportunityPage:
        return self.repository.list(search, datetime.now(UTC))

    def get(self, opportunity_id: UUID) -> PublicOpportunity:
        result = self.repository.get(opportunity_id, datetime.now(UTC))
        if result is None:
            raise AppError("NOT_FOUND")
        return result

    def preparation(self, opportunity_id: UUID) -> Preparation:
        # 상세와 같은 공개 포인터/상태를 한 번만 조회한다. 원문 파싱·LLM 추정·외부 요청은 없다.
        opportunity = self.get(opportunity_id)
        fields = set(Preparation.model_fields) - {"opportunity"}
        try:
            return Preparation(
                opportunity=OpportunityRef(id=opportunity.id, version=opportunity.version),
                **opportunity.model_dump(include=fields),
            )
        except ValidationError:
            raise AppError("SERVICE_UNAVAILABLE") from None


class UnavailableOpportunityRepository:
    def list(self, *args):
        raise AppError("SERVICE_UNAVAILABLE")

    get = list
