"""세션에 결합한 일회 state와 허용 로그인 목적. 신원을 브라우저에 반환하지 않는다."""

import base64
from dataclasses import dataclass, field
import hashlib
import re
import secrets
from typing import Literal, Protocol
from urllib.parse import urlencode

from app.adapters.auth import OAuthFailure, OAuthProvider
from app.core.business_errors import AppError
from app.modules.sessions.service import IssuedSession, Session, StoreUnavailable

Purpose = Literal["login", "save", "reauth"]
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


@dataclass(frozen=True)
class Flow:
    purpose: Purpose
    verifier: str = field(repr=False)


@dataclass(frozen=True)
class Identity:
    subject: str = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.subject, str) or re.fullmatch(r"[1-9][0-9]{0,18}", self.subject) is None or int(self.subject) > 2**63 - 1:
            raise OAuthFailure


@dataclass(frozen=True)
class Completion:
    status: Literal["success", "failed", "expired", "cancelled"]
    issued: IssuedSession | None = None


class CompletionHandler(Protocol):
    async def eligible(self, session: Session, purpose: Purpose) -> str | None: ...
    async def complete(self, session: Session, identity: Identity, purpose: Purpose) -> Completion: ...


class UnavailableCompletionHandler:
    """#73/#74 연결 전에는 로그인/저장/재인증 성공을 만들어 내지 않는다."""
    async def eligible(self, session, purpose):
        return {"save": "expired", "reauth": "failed"}.get(purpose)

    async def complete(self, session, identity, purpose):
        raise OAuthFailure


class UnavailableFlowStore:
    async def create(self, *args):
        raise StoreUnavailable

    consume = create


def state_digest(raw):
    if not isinstance(raw, str) or _TOKEN.fullmatch(raw) is None:
        return None
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


class OAuthService:
    def __init__(self, store, adapter: OAuthProvider | None, completion=None):
        self.store, self.adapter = store, adapter
        self.completion = completion or UnavailableCompletionHandler()

    async def start(self, session, purpose):
        if purpose not in {"login", "save", "reauth"}:
            raise AppError("VALIDATION_FAILED")
        status = await self.completion.eligible(session, purpose)
        if status is not None:
            return result_location(purpose, status)
        if self.adapter is None:
            raise AppError("SERVICE_UNAVAILABLE")
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
        try:
            if not await self.store.create(session.digest, state_digest(state), Flow(purpose, verifier)):
                raise AppError("SERVICE_UNAVAILABLE")
        except StoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None
        return self.adapter.authorization_url(state, challenge, purpose)

    async def callback(self, session, query):
        purpose = "login"
        digest = state_digest(query.get("state"))
        if session is None or digest is None:
            return purpose, Completion("failed")
        try:
            # 외부 교환 전에 원자적으로 소모해 같은 state로 한 요청만 진입한다.
            flow = await self.store.consume(session.digest, digest)
            if flow is None:
                return purpose, Completion("failed")
            purpose = flow.purpose
            allowed = {"state", "code", "error", "error_description"}
            valid = set(query.keys()) <= allowed and all(len(query.getlist(key)) == 1 for key in query.keys())
            valid = valid and all(isinstance(value, str) and value.isascii() and value.isprintable() and len(value) <= limit
                for key, limit in (("code", 512), ("error", 64), ("error_description", 512)) if (value := query.get(key)) is not None)
            if not valid or query.get("code") and query.get("error"):
                return purpose, Completion("failed")
            error = query.get("error")
            if error is not None:
                return purpose, Completion("cancelled" if error == "access_denied" else "failed")
            if not query.get("code") or self.adapter is None:
                return purpose, Completion("failed")
            identity = Identity(await self.adapter.exchange(query["code"], flow.verifier))
            # 외부 I/O 중 세션 회수가 가능하다. 완료 처리기는 재검사 후 원자 전환한다.
            return purpose, await self.completion.complete(session, identity, purpose)
        except (StoreUnavailable, OAuthFailure):
            return purpose, Completion("failed")


def result_location(purpose, status):
    if purpose not in {"login", "save", "reauth"} or status not in {"success", "cancelled", "failed", "expired"}:
        raise OAuthFailure
    return "/auth/result?" + urlencode({"purpose": purpose, "status": status})
