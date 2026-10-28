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
    def __init__(self, accounts, store, sessions, *, transition=None, mfa=None):
        self.accounts, self.store, self.sessions, self.transition = accounts, store, sessions, transition
        # 운영자 MFA 자격 조회. 연결 전이거나 없으면 관리 기능을 열지 않는다.
        self.mfa = mfa

    async def _read(self, session):
        if session.user_id is None:
            return None
        try:
            binding = await self.store.read(session.digest)
        except StoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None
        if binding is None or binding.user_id != session.user_id:
            raise AppError("SESSION_EXPIRED")
        if session.user_generation is not None and binding.generation != session.user_generation:
            raise AppError('SESSION_EXPIRED')
        account = await asyncio.to_thread(self.accounts.get, binding.user_id)
        if account is None or account.generation != binding.generation:
            raise AppError("SESSION_EXPIRED")
        try:
            latest = await self.store.read(session.digest)
        except StoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None
        if latest is None or latest.user_id != binding.user_id or latest.generation != account.generation:
            raise AppError("SESSION_EXPIRED")
        return account, latest

    async def require(self, session, *, reauth=False, operator=False):
        record = await self._read(session)
        if record is None:
            raise AppError("UNAUTHENTICATED")
        account, binding = record
        if operator and account.role != "admin":
            raise AppError("FORBIDDEN")
        if operator and not await self._mfa_active(account, binding):
            raise AppError("MFA_REQUIRED")
        if reauth and binding.reauth_until_ms <= binding.now_ms:
            raise AppError("REAUTH_REQUIRED")
        return account

    async def _mfa_active(self, account, binding):
        """이 세션의 MFA 확인이 유효한지. 만료·역할 회수·재등록(자격 ID 변경)이면 거짓이다."""
        if account.role != "admin" or binding.mfa_credential is None or binding.mfa_until_ms <= binding.now_ms or self.mfa is None:
            return False
        return await asyncio.to_thread(self.mfa.credential_id, account.id) == binding.mfa_credential

    async def elevate(self, session, account, credential_id):
        """MFA 성공 뒤 권한 상승. 새 세션·CSRF로 교체하고 새 세션에만 MFA 확인을 기록한다."""
        issued = await self._switch(session, account.id, generation=account.generation)
        try:
            until = await self.store.mark_mfa(issued.session.digest, account.id, account.generation, credential_id)
            latest = await asyncio.to_thread(self.accounts.get, account.id)
        except StoreUnavailable:
            await self._discard_quietly(issued)
            raise AppError("SERVICE_UNAVAILABLE") from None
        except AppError:
            await self._discard_quietly(issued)
            raise
        if until is None or latest is None or latest.generation != account.generation or latest.role != "admin":
            await self._discard_quietly(issued)
            raise AppError("SESSION_EXPIRED")
        return issued, until

    async def _discard_quietly(self, issued):
        try:
            await self.store.discard(issued.session)
        except (AppError, StoreUnavailable):
            pass  # 새 쿠키를 응답하지 않으므로 남은 세션도 쓰이지 않는다.

    async def me(self, session):
        record = await self._read(session)
        if record is None:
            return {"authenticated": False, "user": None, "consents": [], "pending_save_intent": None}
        account, binding = record
        until = datetime.fromtimestamp(binding.reauth_until_ms / 1000, UTC).isoformat().replace("+00:00", "Z") if binding.reauth_until_ms > binding.now_ms else None
        return {"authenticated": True, "user": {"id": str(account.id), "roles": ["operator" if account.role == "admin" else "user"],
            "mfa_verified": await self._mfa_active(account, binding), "reauth_until": until}, "consents": [], "pending_save_intent": None}

    async def eligible(self, session, purpose):
        if purpose == "save":
            return None if await self.save_reference(session) is not None else 'expired'
        if purpose == "reauth":
            try:
                return None if await self._read(session) is not None else "failed"
            except AppError:
                return "failed"
        return None

    async def save_reference(self, session):
        service = getattr(self, 'save_intents', None)
        return await service.reference(session) if service is not None else None

    async def discard_save(self, session, identity):
        service = getattr(self, 'save_intents', None)
        if service is not None:
            await service.store.discard(session, identity)

    async def pending_save(self, session):
        service = getattr(self, 'save_intents', None)
        if service is None:
            return None
        account = await self.require(session)
        return await service.pending(session, account)

    async def _switch(self, session, user_id=None, *, perform_cleanup=True, save_intent_id=None, generation=0):
        if perform_cleanup and self.transition is not None:
            await self.transition(session)
        token, secret, subject = secrets.token_urlsafe(32), secrets.token_hex(32), uuid4()
        try:
            options = {'save_intent_id': save_intent_id} if save_intent_id is not None else {}
            options.update(generation=generation, old_user_id=session.user_id)
            replacement = await self.store.switch(session.digest, token_digest(token), subject, secret, user_id, **options)
        except StoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None
        if replacement is None:
            raise AppError("SESSION_EXPIRED")
        service = getattr(self, 'save_intents', None)
        if session.user_id is not None and service is not None:
            try:
                # 인증 회수 뒤 진행 중 SQL 저장과 직렬화한 후에만 전환 성공을 반환한다.
                await service.drain(session)
            except BaseException:
                await self.sessions.revoke(token)
                raise
        return IssuedSession(replacement, token)

    async def complete(self, session, identity, purpose, *, save_intent_id=None):
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
            if purpose == 'save' and (save_intent_id is None or await self.save_reference(current) != save_intent_id):
                return Completion('expired')
            if purpose not in {"login", 'save'}:
                return Completion("expired")
            account = await asyncio.to_thread(self.accounts.link, identity)
            issued = await self._switch(current, account.id, save_intent_id=save_intent_id, generation=account.generation)
            # 저장소 사이의 정지·삭제는 최종 확인과 중요 요청마다의 DB 조회로 차단한다.
            latest = await asyncio.to_thread(self.accounts.get, account.id)
            if latest is None or latest.generation != account.generation:
                await self.sessions.revoke(issued.token)
                raise OAuthFailure
            return Completion("success", issued)
        except (AppError, StoreUnavailable):
            if issued is not None:
                try:
                    await self.store.discard(issued.session)
                except (AppError, StoreUnavailable):
                    pass  # 쿠키를 반환하지 않는다. Redis 장애 시에도 인증 성공으로 응답하지 않는다.
            raise OAuthFailure from None

    async def logout(self, session):
        # 정리 대기/실패와 무관하게 이전 인증을 먼저 원자 회수한다.
        issued = None
        try:
            issued = await self._switch(session, perform_cleanup=False)
            if self.transition is not None:
                await self.transition(session)
            return issued
        except Exception:
            try:
                await self.sessions.store.revoke(session.digest)
                if issued is not None:
                    await self.sessions.revoke(issued.token)
            except StoreUnavailable:
                raise AppError("SERVICE_UNAVAILABLE") from None
            raise AppError("SERVICE_UNAVAILABLE") from None
