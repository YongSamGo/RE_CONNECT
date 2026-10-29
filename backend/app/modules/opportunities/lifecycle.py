"""공고 마감·확인 지연 및 수집 상태의 순수 규칙 (W06-05).

검수 승인·공식 출처/접수 경로·중요 변경 검사는 공개/추천 서비스가 별도로 수행한다.
이 함수의 추천 가능은 시간·모집 상태만 충족한다는 뜻이다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, model_validator

from app.contracts.fields import CONTRACT_CONFIG
from app.contracts.opportunity import OpportunityContent, RecruitmentStatus
from app.contracts.time import UtcDatetime, kst_date, to_utc

MAX_CHECK_DELAY = timedelta(hours=48)
HoldReason = Literal["closed", "recruitment_unknown", "never_checked", "future_check", "stale"]


@dataclass(frozen=True)
class LifecycleDecision:
    recruitment_status: RecruitmentStatus
    recommendation_allowed: bool
    hold_reasons: tuple[HoldReason, ...]
    deadline_time_unconfirmed: bool


def assess_lifecycle(
    content: OpportunityContent, *, source_checked_at: datetime | None, now: datetime,
) -> LifecycleDecision:
    """읽은 공고 자체의 마지막 정상 확인 시각을 사용한다. 출처 성공 시각으로 대체하지 않는다.

    날짜만 있는 마감은 해당 한국 날짜가 지나야 종료다. 정확한 마감 시각은 도달하면
    종료한다. 수집 실패/누락 여부는 모집 상태를 바꾸지 않는다. 48시간 '초과'만 보류다.
    """
    now = to_utc(now)
    status = content.recruitment_status
    precise_deadline = to_utc(content.deadline_at) if content.deadline_at is not None else None
    if precise_deadline is not None:
        if now >= precise_deadline:
            status = "closed"
    elif content.deadline_date is not None and kst_date(now) > content.deadline_date:
        status = "closed"

    reasons: list[HoldReason] = []
    if status == "closed":
        reasons.append("closed")
    elif status == "unknown":
        reasons.append("recruitment_unknown")
    if source_checked_at is None:
        reasons.append("never_checked")
    else:
        checked = to_utc(source_checked_at)
        if checked > now:
            reasons.append("future_check")
        elif now - checked > MAX_CHECK_DELAY:
            reasons.append("stale")

    return LifecycleDecision(
        recruitment_status=status,
        recommendation_allowed=not reasons,
        hold_reasons=tuple(reasons),
        deadline_time_unconfirmed=(
            content.deadline_date is not None and precise_deadline is None
            and kst_date(now) == content.deadline_date and status != "closed"
        ),
    )


class CollectionState(BaseModel):
    """출처 단위 이력. 원문·에러 메시지·개인정보를 담지 않는다."""

    model_config = CONTRACT_CONFIG

    last_attempt_at: UtcDatetime | None
    last_success_at: UtcDatetime | None
    last_result: Literal["never", "success", "failed"]

    @model_validator(mode="after")
    def _chronology(self) -> "CollectionState":
        if self.last_result == "never":
            if self.last_attempt_at is not None or self.last_success_at is not None:
                raise ValueError("미실행 상태의 수집 시각")
        elif self.last_attempt_at is None:
            raise ValueError("수집 시도 시각 필요")
        if self.last_success_at is not None:
            if self.last_attempt_at is None or self.last_success_at > self.last_attempt_at:
                raise ValueError("수집 성공 시각의 순서 오류")
        if self.last_result == "success" and self.last_success_at != self.last_attempt_at:
            raise ValueError("성공 시각과 시도 시각 불일치")
        return self


def record_collection_attempt(
    previous: CollectionState, *, attempted_at: datetime, succeeded: bool,
) -> CollectionState:
    """실패는 마지막 성공 시각을 유지한다. 일시 누락은 공고 종료 이벤트가 아니다.

    여기서 공고별 source_checked_at을 일괄 갱신하지 않는다. 실제 관측한 공고만 수집기가
    갱신해야 한다. 병렬 실행의 저장 CAS·실행 ID는 수집 실행 저장소에서 처리한다(#49).
    """
    attempted_at = to_utc(attempted_at)
    if type(succeeded) is not bool:
        raise ValueError("수집 성공 여부는 불리언이어야 합니다")
    if previous.last_attempt_at is not None and attempted_at <= previous.last_attempt_at:
        raise ValueError("지난 수집 결과로 상태를 덮어쓸 수 없습니다")
    return CollectionState(
        last_attempt_at=attempted_at,
        last_success_at=attempted_at if succeeded else previous.last_success_at,
        last_result="success" if succeeded else "failed",
    )
