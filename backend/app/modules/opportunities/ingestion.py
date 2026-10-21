"""이미 정규화한 공고의 저장 경계. 수집 HTTP/운영자 인가를 대신하지 않는다."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel

from app.contracts.fields import CONTRACT_CONFIG, text
from app.contracts.time import UtcDatetime, utc_now
from app.core.business_errors import AppError
from app.modules.opportunities.lifecycle import assess_lifecycle
from app.modules.opportunities.versions import OpportunitySnapshot


class RecordOpportunity(BaseModel):
    model_config = CONTRACT_CONFIG
    source_id: UUID
    external_id: text(200) | None
    snapshot: OpportunitySnapshot
    checked_at: UtcDatetime
    manual_target: UUID | None = None


@dataclass(frozen=True)
class RecordResult:
    opportunity_id: UUID
    version: int
    outcome: Literal["created", "changed", "closed", "unchanged", "stale"]


class IngestionRepository(Protocol):
    def record(self, command: RecordOpportunity) -> RecordResult: ...


class IngestionService:
    def __init__(self, repository: IngestionRepository, *, clock=utc_now):
        self.repository = repository
        self.clock = clock

    def record(self, command: RecordOpportunity) -> RecordResult:
        now: datetime = self.clock()
        if command.checked_at > now or command.external_id is not None and command.manual_target is not None:
            raise AppError("VALIDATION_FAILED")
        content = command.snapshot
        lifecycle = assess_lifecycle(content, source_checked_at=command.checked_at, now=now)
        if lifecycle.recruitment_status != content.recruitment_status:
            content = content.model_copy(update={"recruitment_status": lifecycle.recruitment_status})
            command = command.model_copy(update={"snapshot": content})
        return self.repository.record(command)


class UnavailableIngestionRepository:
    def record(self, command):
        raise AppError("SERVICE_UNAVAILABLE")
