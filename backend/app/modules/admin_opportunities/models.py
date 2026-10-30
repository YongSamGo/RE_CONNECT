"""운영자 공고 API 계약 (docs/api/openapi.yaml `/admin/opportunities`)."""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt, field_validator

from app.contracts.fields import CONTRACT_CONFIG, SkillTag, Unique, text
from app.contracts.opportunity import OpportunityContent, RecruitmentStatus, RoleId
from app.contracts.time import UtcDatetime
from app.modules.ingestion.manual import Evidence

ReviewStatus = Literal["pending", "approved", "rejected", "hidden"]


class AdminCatalogRole(BaseModel):
    model_config = CONTRACT_CONFIG
    id: RoleId
    name: text(50)
    description: text(300)
    skill_tags: Annotated[list[SkillTag], Field(max_length=20), Unique]


class AdminRoleCatalog(BaseModel):
    """운영 DB의 역할 사전. 검수자가 공고의 역할·역량을 명시적으로 고른다."""

    model_config = CONTRACT_CONFIG
    items: list[AdminCatalogRole] = Field(max_length=500)

# 수동 등록은 공식 자료 수동 출처만 받는다. 출처 UUID 대신 고정 코드로 고른다.
ManualSource = Literal["manual_50plus", "manual_work24", "manual_volunteer"]


class AdminOpportunitySearch(BaseModel):
    model_config = CONTRACT_CONFIG
    review_status: ReviewStatus | None = None
    recruitment_status: RecruitmentStatus | None = None
    important_change: bool | None = None
    q: text(100) | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=20)


class OpportunityCreate(BaseModel):
    """공식 자료 수동 등록. 근거 규칙은 `python -m app.manual_intake`와 같다(docs/data/manual-intake.md)."""

    model_config = CONTRACT_CONFIG
    source: ManualSource
    content: OpportunityContent
    evidence: Evidence


class OpportunityPatch(BaseModel):
    model_config = CONTRACT_CONFIG
    base_version: StrictInt = Field(ge=1)
    # 바꿀 필드만. 값 검사는 기준 버전과 합친 뒤 OpportunityContent 전체 규칙으로 한다.
    changes: dict[str, Any] = Field(min_length=1)

    @field_validator("changes")
    @classmethod
    def _known_fields(cls, changes):
        if not changes.keys() <= OpportunityContent.model_fields.keys():
            raise ValueError("바꿀 수 없는 필드")
        return changes


class AdminSource(BaseModel):
    model_config = CONTRACT_CONFIG
    source_id: UUID
    name: str
    external_id: str | None


class AdminOpportunitySummary(BaseModel):
    model_config = CONTRACT_CONFIG
    id: UUID
    version: int
    title: str
    organization_name: str
    review_status: ReviewStatus
    recruitment_status: RecruitmentStatus
    published_version: int | None
    important_change: bool
    source_checked_at: UtcDatetime
    updated_at: UtcDatetime


class AdminOpportunityList(BaseModel):
    model_config = CONTRACT_CONFIG
    items: list[AdminOpportunitySummary]
    page: int
    page_size: int
    total: int


class AdminOpportunity(BaseModel):
    model_config = CONTRACT_CONFIG
    id: UUID
    version: int
    review_status: ReviewStatus
    published_version: int | None
    source: AdminSource
    changed_fields: list[str]
    important_change: bool
    content: OpportunityContent
    published_content: OpportunityContent | None
    source_checked_at: UtcDatetime
    updated_at: UtcDatetime
