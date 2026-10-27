"""불투명 익명 세션과 자원 소유권 경계 (W03-01).

쿠키 원문은 HTTP로만 전달한다. Redis에는 SHA-256 인덱스와 최소 주체/수명 정보를 보관한다.
CSRF 쿠키 발급은 /me 계약을 위해 제공하며 변경 요청 검증·Origin 검사는 #22에서 연결한다.
"""

from dataclasses import dataclass, field
import hashlib
import hmac
import re
import secrets
from typing import Protocol
from uuid import UUID, uuid4

from app.core.business_errors import AppError

IDLE_MS = 30 * 60 * 1000
ABSOLUTE_MS = 12 * 60 * 60 * 1000
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_CSRF = re.compile(r"([A-Za-z0-9_-]{43})\.([0-9a-f]{64})")


@dataclass(frozen=True)
class Session:
    subject_id: UUID
    created_ms: int
    last_activity_ms: int
    now_ms: int
    csrf_secret: str = field(repr=False)
    digest: str = field(repr=False)
    user_id: UUID | None = None
    user_generation: int | None = None


@dataclass(frozen=True)
class IssuedSession:
    session: Session
    token: str = field(repr=False)


class StoreUnavailable(Exception):
    pass


def parse_session(values, digest):
    if not values:
        return None
    try:
        generation = None
        if len(values) == 7:
            subject, created, last, secret, now, user, generation = values
            generation = int(generation) if generation != '' else None
        elif len(values) == 6:
            subject, created, last, secret, now, user = values
        else:
            subject, created, last, secret, now = values
            user = ""
        created, last, now = int(created), int(last), int(now)
        if not 0 <= created <= last <= now or not re.fullmatch(r"[0-9a-f]{64}", secret):
            raise ValueError
        if generation is not None and (not user or not 0 <= generation < 2147483647): raise ValueError
        return Session(UUID(subject), created, last, now, secret, digest, UUID(user) if user else None, generation)
    except (ValueError, TypeError):
        raise StoreUnavailable from None


class SessionStore(Protocol):
    async def create(self, digest: str, subject_id: UUID, csrf_secret: str) -> Session | None: ...
    async def load(self, digest: str, *, touch: bool) -> Session | None: ...
    async def rotate(self, old_digest: str, new_digest: str, csrf_secret: str) -> Session | None: ...
    async def revoke(self, digest: str) -> None: ...


class UnavailableSessionStore:
    async def create(self, *args, **kwargs):
        raise StoreUnavailable

    load = create
    rotate = create
    revoke = create


def token_digest(token: str | None) -> str | None:
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class SessionService:
    def __init__(self, store: SessionStore):
        self.store = store

    async def issue(self) -> IssuedSession:
        try:
            for _ in range(3):
                token = secrets.token_urlsafe(32)
                session = await self.store.create(token_digest(token), uuid4(), secrets.token_hex(32))
                if session is not None:
                    return IssuedSession(session, token)
        except StoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None
        raise AppError("SERVICE_UNAVAILABLE")

    async def resolve(self, token: str | None, *, touch: bool = False) -> Session | None:
        digest = token_digest(token)
        if digest is None:
            return None
        try:
            return await self.store.load(digest, touch=touch)
        except StoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None

    async def rotate(self, token: str | None) -> IssuedSession:
        digest = token_digest(token)
        if digest is None:
            raise AppError("NOT_FOUND")
        replacement = secrets.token_urlsafe(32)
        try:
            session = await self.store.rotate(digest, token_digest(replacement), secrets.token_hex(32))
        except StoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None
        if session is None:
            raise AppError("NOT_FOUND")
        return IssuedSession(session, replacement)

    async def revoke(self, token: str | None) -> None:
        digest = token_digest(token)
        if digest is not None:
            try:
                await self.store.revoke(digest)
            except StoreUnavailable:
                raise AppError("SERVICE_UNAVAILABLE") from None


def require_owner(session: Session | None, owner_id: UUID | None) -> Session:
    """없는 자원·다른 주체·세션 없음은 같은 사적 404다. 소유자는 저장소에서 읽는다."""
    if session is None or owner_id is None or session.subject_id != owner_id:
        raise AppError("NOT_FOUND")
    return session


def csrf_token(session: Session) -> str:
    nonce = secrets.token_urlsafe(32)
    signature = _csrf_signature(session, nonce)
    return f"{nonce}.{signature}"


def _csrf_signature(session: Session, nonce: str) -> str:
    message = f"reconnect/csrf/v1:{session.digest}:{nonce}".encode("ascii")
    return hmac.new(bytes.fromhex(session.csrf_secret), message, hashlib.sha256).hexdigest()


def valid_csrf_cookie(session: Session, value: str | None) -> bool:
    match = _CSRF.fullmatch(value) if isinstance(value, str) else None
    return match is not None and hmac.compare_digest(_csrf_signature(session, match[1]), match[2])
