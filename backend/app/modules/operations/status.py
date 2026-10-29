"""운영자용 수집·모델·저장소·추론 한도 상태 (`GET /admin/operations`, W07-04).

응답에는 고정 코드·시각·건수만 담는다. 오류 메시지·주소·비밀값·개인 본문은 넣지 않는다.
한 구성 요소를 읽지 못해도 나머지 상태는 그대로 돌려준다. 운영 화면은 장애 때 가장 필요하기 때문이다.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, datetime
import logging
from typing import Annotated, Literal, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.time import kst_date, to_utc, utc_now
from app.modules.admission.service import GLOBAL_DAILY_LIMIT, SHARED_SLOTS
from app.modules.operations.readiness import ReadinessProbe
from app.modules.operations.repository import SourceRunSummary
from app.modules.opportunities.lifecycle import MAX_CHECK_DELAY

logger = logging.getLogger(__name__)

T = TypeVar("T")

# `loading`은 계약에 남겨 둔 값이다. 지금 음성 서비스·Ollama는 적재 중을 따로 알려 주지 않아 쓰지 않는다.
ComponentState = Literal["ok", "loading", "fail"]
SourceRunStatus = Literal["success", "partial", "failed"]
FailureCode = Literal[
    "network", "parse", "response_limit", "source_unavailable", "cancelled",
    "invalid_payload", "budget_exhausted", "incomplete", "configuration",
]
# 일부만 받은 뒤 멈춘 실패. 받은 공고는 저장됐지만 출처 전체를 다시 확인하지는 못했다.
PARTIAL_FAILURES: frozenset[str] = frozenset({"budget_exhausted", "incomplete"})
EPOCH_DATE = date(1970, 1, 1)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceStatus(_Strict):
    source_id: UUID
    name: Annotated[str, Field(min_length=1, max_length=200)]
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_status: SourceRunStatus | None
    last_failure_code: FailureCode | None
    running: bool
    consecutive_failures: Annotated[int, Field(ge=0)]
    stale: bool


class ModelStates(_Strict):
    llm: ComponentState
    stt: ComponentState
    tts: ComponentState


class StoreStates(_Strict):
    db: ComponentState
    redis: ComponentState


class InferenceLimits(_Strict):
    inference_today: Annotated[int, Field(ge=0)]
    inference_daily_limit: Annotated[int, Field(ge=0)]
    slots_in_use: Annotated[int, Field(ge=0)]
    slots_total: Annotated[int, Field(ge=0)]


class Operations(_Strict):
    sources: list[SourceStatus] | None
    models: ModelStates
    stores: StoreStates
    limits: InferenceLimits | None
    checked_at: datetime


class SourceStatusReader(Protocol):
    def list(self) -> list[SourceRunSummary]: ...


class SpeechModels(Protocol):
    async def model_readiness(self) -> dict[str, bool]: ...


class SlotReading(Protocol):
    ready: bool
    day: int | None
    global_count: int | None
    lease: str | None


class SlotReader(Protocol):
    async def read(self) -> SlotReading: ...


class AdmissionSlotStore(Protocol):
    async def slot_status(self, identity_key_id: str) -> SlotReading: ...


class BoundSlotReader:
    """추론 제어 저장소의 슬롯 상태를 현재 한도 식별키로 읽는다."""

    def __init__(self, store: AdmissionSlotStore, identity_key_id: str) -> None:
        self._store, self._identity_key_id = store, identity_key_id

    async def read(self) -> SlotReading:
        return await self._store.slot_status(self._identity_key_id)


def kst_day_index(now: datetime) -> int:
    """Redis 제어 해시의 `day`와 같은 기준(1970-01-01 KST부터 센 날 수)."""
    return (kst_date(now) - EPOCH_DATE).days


def last_status(summary: SourceRunSummary) -> SourceRunStatus | None:
    if summary.last_finished_status is None:
        return None
    if summary.last_finished_status == "succeeded":
        return "success"
    return "partial" if summary.last_failure_code in PARTIAL_FAILURES else "failed"


def source_status(summary: SourceRunSummary, now: datetime) -> SourceStatus:
    succeeded = summary.last_finished_status == "succeeded"
    return SourceStatus(
        source_id=summary.source_id,
        name=summary.name,
        last_run_at=summary.last_finished_at,
        last_success_at=summary.last_success_at,
        last_status=last_status(summary),
        last_failure_code=None if succeeded else summary.last_failure_code,
        running=summary.running,
        consecutive_failures=summary.consecutive_failures,
        # 공고별 추천 보류와 같은 48시간 '초과' 기준. 성공한 적이 없으면 신선하지 않다.
        stale=summary.last_success_at is None or now - to_utc(summary.last_success_at) > MAX_CHECK_DELAY,
    )


def inference_limits(reading: SlotReading, now: datetime) -> InferenceLimits | None:
    """제어 상태를 믿을 수 없거나 형식이 어긋나면 숫자를 꾸미지 않고 None을 돌려준다."""
    if reading.ready is not True or reading.day is None or reading.global_count is None:
        return None
    # 오늘 첫 실행 전에는 어제 집계가 남아 있다. 실행 시 Redis가 0으로 바꾼다.
    today = reading.global_count if reading.day >= kst_day_index(now) else 0
    return InferenceLimits(
        inference_today=today,
        inference_daily_limit=GLOBAL_DAILY_LIMIT,
        slots_in_use=1 if reading.lease is not None else 0,
        slots_total=SHARED_SLOTS,
    )


def _state(ready: bool) -> ComponentState:
    return "ok" if ready else "fail"


class OperationsService:
    def __init__(
        self,
        *,
        db: ReadinessProbe,
        redis: ReadinessProbe,
        inference_control: ReadinessProbe,
        llm: ReadinessProbe,
        speech: SpeechModels,
        slots: SlotReader | None,
        sources: SourceStatusReader | None,
        timeout_seconds: float,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not timeout_seconds > 0:
            raise ValueError("상태 확인 제한시간은 0보다 커야 합니다")
        self._db, self._redis, self._control, self._llm = db, redis, inference_control, llm
        self._speech, self._slots, self._sources = speech, slots, sources
        self._timeout, self._clock = timeout_seconds, clock

    async def _bounded(self, part: str, call: Callable[[], Awaitable[T]], default: T) -> T:
        try:
            return await asyncio.wait_for(call(), self._timeout)
        except Exception as exc:  # 읽지 못한 구성 요소는 기본값으로 둔다. 오류 내용은 응답·로그에 넣지 않는다.
            logger.warning("운영 상태 확인 실패: part=%s type=%s", part, type(exc).__name__)
            return default

    async def _ready(self, part: str, probe: ReadinessProbe) -> bool:
        return await self._bounded(part, probe.is_ready, False) is True

    async def _speech_models(self) -> dict[str, bool]:
        states = await self._bounded("speech", self._speech.model_readiness, {})
        return {name: states.get(name) is True for name in ("stt", "tts")}

    async def _slot_reading(self) -> SlotReading | None:
        if self._slots is None:
            return None
        return await self._bounded("limits", self._slots.read, None)

    async def _source_summaries(self) -> list[SourceRunSummary] | None:
        if self._sources is None:
            return None
        return await self._bounded("sources", lambda: asyncio.to_thread(self._sources.list), None)

    async def check(self) -> Operations:
        db, redis, control, llm, speech, reading, summaries = await asyncio.gather(
            self._ready("db", self._db),
            self._ready("redis", self._redis),
            self._ready("inference_control", self._control),
            self._ready("llm", self._llm),
            self._speech_models(),
            self._slot_reading(),
            self._source_summaries(),
        )
        now = to_utc(self._clock())
        # 모델이 떠 있어도 공유 추론 제어가 준비되지 않으면 요청을 받을 수 없다. /health/ready와 같은 판정이다.
        models = ModelStates(
            llm=_state(control and llm),
            stt=_state(control and speech["stt"]),
            tts=_state(control and speech["tts"]),
        )
        sources = None
        if summaries is not None:
            try:
                sources = [source_status(summary, now) for summary in summaries]
            except ValueError as exc:  # 저장값이 계약과 어긋나면 일부만 고쳐 보여 주지 않는다.
                logger.warning("운영 상태 확인 실패: part=sources type=%s", type(exc).__name__)
        limits = None
        if reading is not None:
            try:
                limits = inference_limits(reading, now)
            except (ValueError, TypeError) as exc:
                logger.warning("운영 상태 확인 실패: part=limits type=%s", type(exc).__name__)
        return Operations(
            sources=sources,
            models=models,
            stores=StoreStates(db=_state(db), redis=_state(redis)),
            limits=limits,
            checked_at=now,
        )
