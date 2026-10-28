"""공개 조회 계약. 읽기는 세션·AI·Redis와 무관하게 DB 공개 포인터를 따른다."""

from __future__ import annotations

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
    regions: list[str] = Field(default_factory=list, max_length=67)
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

    @field_validator("regions")
    @classmethod
    def _regions_known(cls, values):
        parsed: list[tuple[Province, str | None]] = []
        for value in values:
            parts = value.split(":")
            if len(parts) not in (1, 2) or parts[0] not in ("seoul", "gyeonggi", "incheon"):
                raise PydanticCustomError("invalid_region_filter", "지역 필터 형식이 올바르지 않습니다")
            province = parts[0]
            district = parts[1] if len(parts) == 2 else None
            if district == "":
                raise PydanticCustomError("invalid_region_filter", "지역 필터 형식이 올바르지 않습니다")
            if district is not None and not is_known_district(province, district):
                raise PydanticCustomError("unknown_district", "지역 목록에 없는 시·군·구")
            parsed.append((province, district))
        if len(set(parsed)) != len(parsed):
            raise PydanticCustomError("duplicate_region_filter", "같은 지역을 중복 선택할 수 없습니다")
        for province, district in parsed:
            if district is None and any(other == province and other_district is not None for other, other_district in parsed):
                raise PydanticCustomError("overlapping_region_filter", "시·도 전체와 그 안의 시·군·구를 함께 선택할 수 없습니다")
        return values

    @model_validator(mode="after")
    def _region_filters_exclusive(self):
        if self.regions and (self.province is not None or self.district is not None):
            raise PydanticCustomError("conflicting_region_filter", "regions와 province/district 필터를 함께 사용할 수 없습니다")
        return self


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
    def recommendation_candidates(self, now: datetime) -> list[PublicOpportunity]: ...


class PublicOpportunityService:
    def __init__(self, repository: PublicOpportunityRepository):
        self.repository = repository

    def list(self, search: OpportunitySearch) -> OpportunityPage:
        return self.repository.list(search, datetime.now(UTC))

    def recommendation_candidates(self, now: datetime) -> list[PublicOpportunity]:
        return self.repository.recommendation_candidates(now)

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

    get = recommendation_candidates = list
