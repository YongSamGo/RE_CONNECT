"""감사 기록 조회·정리. 기준 시각은 서버 시계이며 요청에서 받지 않는다."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from app.contracts.time import utc_now
from app.modules.audit.models import AuditList, AuditSearch


class AuditRepository(Protocol):
    def page(self, search: AuditSearch, now: datetime) -> AuditList: ...

    def prune(self, now: datetime) -> int: ...


class AuditService:
    def __init__(self, repository: AuditRepository, *, clock: Callable[[], datetime] = utc_now):
        self.repository, self.clock = repository, clock

    def page(self, search: AuditSearch) -> AuditList:
        return self.repository.page(search, self.clock())

    def prune(self) -> int:
        """보관기간(30일)이 지난 기록을 지운다. 주기 실행은 #96(W12-07)에서 연결한다."""
        return self.repository.prune(self.clock())
