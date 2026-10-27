"""운영자 검수 상태 전이 규칙 (W07-03, openapi 운영자 경로).

- 승인·반려: 그 공고의 최신 버전이면서 `pending`인 버전만. 더 새 버전이 있으면 VERSION_CONFLICT.
- 비공개·모집 종료: 지금 공개 중인 버전만. 공개본이 없으면 INVALID_STATE_TRANSITION.
- `rejected`·`hidden`은 그 버전에서 끝난다. 다시 공개하려면 새 `pending` 버전을 만들어 승인한다.
- 모집 종료는 공개본과 그 뒤의 `pending` 버전을 함께 닫는다. 종료 전에 들어온 "모집 중" 버전을
  나중에 승인해도 조용히 다시 열리지 않게 하기 위해서다.
- 상태 변경·검수 근거·감사 기록은 한 트랜잭션이다. 감사 기록을 못 남기면 상태도 바꾸지 않는다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.modules.ingestion.manual import official_url
from app.modules.ingestion.normalize import UNREVIEWED_EVIDENCE_PREFIX
from app.modules.opportunities.lifecycle import assess_lifecycle
from app.modules.opportunities.versions import OpportunitySnapshot
from app.modules.opportunity_reviews.models import (
    ApproveRequest, CloseRequest, HideRequest, RejectRequest, ReviewCommand, ReviewResult,
)

FieldReason = Literal["required", "invalid_value"]


@dataclass(frozen=True)
class FieldProblem:
    path: str
    reason: FieldReason


class NotPublishable(Exception):
    """공개 필수 항목이 비었거나 공개할 수 없는 값이다. 경로와 사유만 담고 값은 담지 않는다."""

    def __init__(self, problems: tuple[FieldProblem, ...]):
        super().__init__("not publishable")
        self.problems = problems


def publishability_problems(snapshot: OpportunitySnapshot, *, now: datetime) -> tuple[FieldProblem, ...]:
    """제목·기관·접수 경로·HTTPS 형식은 저장 계약이 이미 보장한다. 여기서는 공개 시점 조건만 본다.

    수집기가 넣은 "필수조건 미검수" 표식 조건이 남아 있으면 승인하지 않는다. 운영자가 PATCH로 조건을 구조화하거나
    "명시된 필수조건 없음"을 확인해 표식을 지운 새 버전을 만들어야 한다.

    원문 주소는 출처별 공식 상세 경로 허용표(수집기·수동 입력과 같은 표)에 맞아야 한다. 자동 수집 출처의
    base_url은 API 주소라 원문 호스트와 다르므로 출처 주소와의 비교로 대신하지 않는다.
    """
    problems = []
    if snapshot.activity_region is None and snapshot.remote_allowed is not True:
        problems.append(FieldProblem("content.activity_region", "required"))
    # 수집기의 미검수 표식이 남아 있으면 원문 연령·자격 제한이 자격 판정에서 빠진 채 추천된다.
    # 원문을 해석할 수 없어 남긴 다른 `other` 조건은 검수를 마친 최종 상태이므로 막지 않는다.
    if any(r.field == "other" and r.source_evidence.startswith(UNREVIEWED_EVIDENCE_PREFIX) for r in snapshot.requirements):
        problems.append(FieldProblem("content.requirements", "invalid_value"))
    try:
        official_url(snapshot.source_url)
    except ValueError:
        problems.append(FieldProblem("content.source_url", "invalid_value"))
    # 마감이 지났거나 종료된 공고는 공개하지 않는다. 확인 지연(48시간)은 추천에서만 보류한다.
    lifecycle = assess_lifecycle(snapshot, source_checked_at=None, now=now)
    if lifecycle.recruitment_status == "closed":
        problems.append(FieldProblem("content.recruitment_status", "invalid_value"))
    return tuple(problems)


Check = Callable[[OpportunitySnapshot, datetime], None]


class OpportunityReviewRepository(Protocol):
    def apply(self, opportunity_id: UUID, command: ReviewCommand, check: Check | None = None) -> ReviewResult: ...


def check_publishable(snapshot: OpportunitySnapshot, now: datetime) -> None:
    problems = publishability_problems(snapshot, now=now)
    if problems:
        raise NotPublishable(problems)


class OpportunityReviewService:
    def __init__(self, repository: OpportunityReviewRepository, *, clock: Callable[[], datetime] = utc_now):
        self.repository, self.clock = repository, clock

    def _command(self, action, body, actor_id, request_id, reason_code=None):
        return ReviewCommand(action=action, base_version=body.base_version, reason_code=reason_code, note=body.note,
                             actor_id=actor_id, request_id=request_id, at=self.clock())

    def approve(self, opportunity_id: UUID, body: ApproveRequest, *, actor_id: UUID, request_id: str) -> ReviewResult:
        return self.repository.apply(opportunity_id, self._command("approve", body, actor_id, request_id), check_publishable)

    def reject(self, opportunity_id: UUID, body: RejectRequest, *, actor_id: UUID, request_id: str) -> ReviewResult:
        return self.repository.apply(opportunity_id, self._command("reject", body, actor_id, request_id, body.reason_code))

    def hide(self, opportunity_id: UUID, body: HideRequest, *, actor_id: UUID, request_id: str) -> ReviewResult:
        return self.repository.apply(opportunity_id, self._command("hide", body, actor_id, request_id))

    def close(self, opportunity_id: UUID, body: CloseRequest, *, actor_id: UUID, request_id: str) -> ReviewResult:
        return self.repository.apply(opportunity_id, self._command("close", body, actor_id, request_id, body.basis))


class UnavailableOpportunityReviewRepository:
    def apply(self, *args, **kwargs):
        raise AppError("SERVICE_UNAVAILABLE")
