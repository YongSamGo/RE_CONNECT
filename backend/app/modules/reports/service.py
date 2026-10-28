"""공고 오류 신고 접수·운영자 처리 (W07-05 · #56, Plan/04 F10).

접수는 비회원도 할 수 있다. 신고자는 DB에 남기지 않고, 한도·멱등 기록에만 HMAC 식별값을 쓴다.
현재 공개 중인 공고의 공개 버전만 받는다. 순서는 멱등 기록 조회 → 공고 확인 → 한도·기록 확정 → 저장이다.
공고 확인이 실패하면 한도를 쓰지 않는다. 저장이 실패해도 같은 멱등 키로 다시 보내면 같은 신고 ID로 저장한다.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.adapters.database import run_query
from app.core.business_errors import AppError
from app.modules.admission.service import normalize_ip
from app.modules.reports.models import AdminReport, AdminReportList, ReportCreate, ReportReceipt, ReportUpdate
from app.modules.reports.store import ReportIdentity
from app.modules.requests.service import input_fingerprint


def _key_id(key: str) -> UUID:
    try:
        key_id = UUID(key)
        if str(key_id) != key.lower():
            raise ValueError
        return key_id
    except (ValueError, TypeError, AttributeError):
        raise AppError("VALIDATION_FAILED") from None


class ReportService:
    def __init__(self, store, repository, opportunities, digest: Callable[[str, str], str] | None, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.store, self.repository, self.opportunities = store, repository, opportunities
        self._digest, self._clock = digest, clock

    def _identity(self, subject_id: UUID, ip: str, opportunity_id: UUID) -> ReportIdentity:
        if self._digest is None:
            raise AppError("SERVICE_UNAVAILABLE")
        return ReportIdentity(subject=self._digest("report-subject", str(subject_id)), ip=self._digest("report-ip", normalize_ip(ip)),
                              subject_opportunity=self._digest("report-subject-opportunity", f"{subject_id}:{opportunity_id}"))

    async def _require_public(self, body: ReportCreate) -> None:
        opportunity = await run_query(self.opportunities.get, body.opportunity.id)
        if opportunity.version != body.opportunity.version:
            raise AppError("VERSION_CONFLICT")

    async def create(self, subject_id: UUID, ip: str, key: str, body: ReportCreate) -> ReportReceipt:
        key_id = _key_id(key)
        identity = self._identity(subject_id, ip, body.opportunity.id)
        fingerprint = input_fingerprint(body.model_dump(mode="json"))
        reservation = await self.store.reserve(identity, key_id, fingerprint, uuid4(), peek=True)
        if reservation is not None and await run_query(self.repository.exists, reservation.report_id):
            return ReportReceipt(report_id=reservation.report_id, received_at=reservation.received_at)
        await self._require_public(body)
        if reservation is None:
            reservation = await self.store.reserve(identity, key_id, fingerprint, uuid4(), peek=False)
        await run_query(self.repository.create, reservation.report_id, reservation.received_at, body)
        return ReportReceipt(report_id=reservation.report_id, received_at=reservation.received_at)

    async def listing(self, status: str | None, page: int, page_size: int) -> AdminReportList:
        return await run_query(self.repository.listing, status, page, page_size)

    async def update(self, report_id: UUID, body: ReportUpdate, *, actor_id: UUID, request_id: str) -> AdminReport:
        return await run_query(lambda: self.repository.update(report_id, body, actor_id=actor_id, request_id=request_id, at=self._clock()))

    async def purge(self, limit: int = 100) -> int:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("정리 건수 범위 오류")
        return await run_query(self.repository.purge, self._clock(), limit)
