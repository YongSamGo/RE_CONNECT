"""운영자 MFA 확인 업무 규칙. 실패·잠금은 저장소가 먼저 확정(commit)한 뒤 오류로 바꾼다."""

import asyncio
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.core.business_errors import AppError


class MfaRepository(Protocol):
    def credential_id(self, user_id: UUID) -> UUID | None: ...
    def verify(self, user_id: UUID, otp: str, now: datetime, request_id: str): ...


class OperatorMfaService:
    def __init__(self, repository: MfaRepository, members, *, clock=lambda: datetime.now(UTC)):
        self.repository, self.members, self.clock = repository, members, clock

    async def verify(self, session, otp: str, request_id: str):
        # 운영자 역할 확인 전에는 OTP를 비교하지 않는다. 역할은 매번 DB에서 읽는다.
        account = await self.members.require(session)
        if account.role != "admin":
            raise AppError("FORBIDDEN")
        result = await asyncio.to_thread(self.repository.verify, account.id, otp, self.clock(), request_id)
        if result.status == "forbidden":
            raise AppError("FORBIDDEN")
        if result.status in ("locked", "blocked"):
            raise AppError("MFA_LOCKED", retry_after=result.retry_after)
        if result.status != "verified" or result.credential_id is None:
            raise AppError("MFA_INVALID")
        return await self.members.elevate(session, account, result.credential_id)
