"""내부 계정·세션 결합. 매 요청 DB 상태/역할 확인, 로그인·재인증은 목적별로 처리한다."""

import asyncio
from datetime import UTC, datetime
import secrets
from uuid import uuid4

from app.adapters.auth import OAuthFailure
from app.core.business_errors import AppError
from app.modules.auth.service import Completion
from app.modules.sessions.service import IssuedSession, StoreUnavailable, token_digest


class MemberService:
    def __init__(self, accounts, store, sessions, *, transition=None):
        self.accounts, self.store, self.sessions, self.transition = accounts, store, sessions, transition

    async def _read(self, session):
        if session.user_id is None:
            return None
        try:
            binding = await self.store.read(session.digest)
        except StoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None
        if binding is None or binding.user_id != session.user_id:
            raise AppError("SESSION_EXPIRED")
        account = await asyncio.to_thread(self.accounts.get, binding.user_id)
        if account is None:
            raise AppError("SESSION_EXPIRED")
        try:
            latest = await self.store.read(session.digest)
        except StoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None
        if latest is None or latest.user_id != binding.user_id:
            raise AppError("SESSION_EXPIRED")
        return account, latest

    async def require(self, session, *, reauth=False, operator=False):
        record = await self._read(session)
        if record is None:
            raise AppError("UNAUTHENTICATED")
        account, binding = record
        if operator and account.role != "admin":
            raise AppError("FORBIDDEN")
        if operator:
            raise AppError("MFA_REQUIRED")  # #52의 실제 세션 결합 MFA 검사 연결 전에는 허용하지 않는다.
        if reauth and binding.reauth_until_ms <= binding.now_ms:
            raise AppError("REAUTH_REQUIRED")
        return account

    async def me(self, session):
        record = await self._read(session)
        if record is None:
            return {"authenticated": False, "user": None, "consents": [], "pending_save_intent": None}
        account, binding = record
        until = datetime.fromtimestamp(binding.reauth_until_ms / 1000, UTC).isoformat().replace("+00:00", "Z") if binding.reauth_until_ms > binding.now_ms else None
        return {"authenticated": True, "user": {"id": str(account.id), "roles": ["operator" if account.role == "admin" else "user"],
            "mfa_verified": False, "reauth_until": until}, "consents": [], "pending_save_intent": None}

    async def eligible(self, session, purpose):
        if purpose == "save":
            return "expired"  # #74에서 실제 저장 대기 검사·이동을 연결한다.
        if purpose == "reauth":
            try:
                return None if await self._read(session) is not None else "failed"
            except AppError:
                return "failed"
        return None

    async def _switch(self, session, user_id=None):
        if self.transition is not None:
            await self.transition(session)
        token, secret, subject = secrets.token_urlsafe(32), secrets.token_hex(32), uuid4()
        try:
            replacement = await self.store.switch(session.digest, token_digest(token), subject, secret, user_id)
        except StoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None
        if replacement is None:
            raise AppError("SESSION_EXPIRED")
        return IssuedSession(replacement, token)

    async def complete(self, session, identity, purpose):
        issued = None
        try:
            # 외부 인증 성공만으로 이전 주체·사용자 ID를 재사용하지 않는다.
            current = await self.sessions.store.load(session.digest, touch=False)
            if current is None or current.subject_id != session.subject_id:
                raise OAuthFailure
            if purpose == "reauth":
                record = await self._read(current)
                account = await asyncio.to_thread(self.accounts.find, identity)
                if record is None or account is None or record[0].id != account.id:
                    raise OAuthFailure
                binding = await self.store.reauth(session.digest, account.id)
                if binding is None:
                    raise OAuthFailure
                return Completion("success")
            if purpose != "login":
                return Completion("expired")
            account = await asyncio.to_thread(self.accounts.link, identity)
            issued = await self._switch(current, account.id)
            # 저장소 사이의 정지·삭제는 최종 확인과 중요 요청마다의 DB 조회로 차단한다.
            if await asyncio.to_thread(self.accounts.get, account.id) is None:
                await self.sessions.revoke(issued.token)
                raise OAuthFailure
            return Completion("success", issued)
        except (AppError, StoreUnavailable):
            if issued is not None:
                try:
                    await self.sessions.revoke(issued.token)
                except AppError:
                    pass  # 쿠키를 반환하지 않는다. Redis 장애 시에도 인증 성공으로 응답하지 않는다.
            raise OAuthFailure from None

    async def logout(self, session):
        # 정지 계정도 자신의 세션을 폐기할 수 있다. 정리 실패 시에도 이전 인증은 회수한다.
        try:
            return await self._switch(session)
        except AppError:
            try:
                await self.sessions.store.revoke(session.digest)
            except StoreUnavailable:
                raise AppError("SERVICE_UNAVAILABLE") from None
            raise
