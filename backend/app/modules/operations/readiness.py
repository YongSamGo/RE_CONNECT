"""준비 상태 확인 서비스.

DB·Redis가 실패하면 `unavailable`(503), 모델·음성만 실패하면 `degraded`(200)로 공개 공고 조회를 계속한다
(docs/api/README.md §2.10). 응답에는 구성 요소별 ok·fail만 담고 오류 내용은 넣지 않는다.
"""

import asyncio
import logging
from collections.abc import Mapping
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

Component = Literal["db", "redis", "llm", "speech"]
CheckResult = Literal["ok", "fail"]

COMPONENTS: tuple[Component, ...] = ("db", "redis", "llm", "speech")
# 이 구성 요소가 실패하면 요청을 받을 수 없다. 나머지는 AI 기능만 저하된다.
REQUIRED_COMPONENTS: frozenset[Component] = frozenset({"db", "redis"})


class ReadinessProbe(Protocol):
    """구성 요소 하나의 준비 여부. LLM·Speech Adapter는 같은 메서드를 가져 그대로 쓸 수 있다."""

    async def is_ready(self) -> bool: ...


class NotConfiguredProbe:
    """아직 연결 구현이 없는 구성 요소. 정상으로 꾸미지 않고 항상 실패로 답한다."""

    async def is_ready(self) -> bool:
        return False


class ReadinessChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    db: CheckResult
    redis: CheckResult
    llm: CheckResult
    speech: CheckResult


class Readiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "degraded", "unavailable"]
    checks: ReadinessChecks


class ReadinessService:
    def __init__(self, probes: Mapping[Component, ReadinessProbe], timeout_seconds: float) -> None:
        missing = set(COMPONENTS) - set(probes)
        if missing:
            raise ValueError(f"상태 확인 대상이 빠졌습니다: {sorted(missing)}")
        self._probes = dict(probes)
        self._timeout_seconds = timeout_seconds

    async def _check(self, component: Component) -> CheckResult:
        try:
            ready = await asyncio.wait_for(self._probes[component].is_ready(), self._timeout_seconds)
        except Exception as exc:  # 확인 실패는 모두 fail로 본다. 오류 내용은 응답에 넣지 않는다.
            logger.warning("상태 확인 실패: component=%s type=%s", component, type(exc).__name__)
            return "fail"
        return "ok" if ready is True else "fail"

    async def check(self) -> Readiness:
        results = await asyncio.gather(*(self._check(component) for component in COMPONENTS))
        checks = dict(zip(COMPONENTS, results, strict=True))

        if any(checks[component] == "fail" for component in REQUIRED_COMPONENTS):
            status: Literal["ready", "degraded", "unavailable"] = "unavailable"
        elif any(result == "fail" for result in results):
            status = "degraded"
        else:
            status = "ready"
        return Readiness(status=status, checks=ReadinessChecks(**checks))
