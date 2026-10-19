"""런타임 종료가 확인되지 않은 실행은 시간만으로 다른 실행에 넘기지 않는다."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import hashlib
import hmac
from ipaddress import ip_address, IPv6Address
import secrets
from typing import Literal, Protocol, TypeVar
from uuid import UUID

from app.core.business_errors import AppError

Kind = Literal["llm", "stt", "tts"]
T = TypeVar("T")


def normalize_ip(value: str) -> str:
    try:
        address = ip_address(value)
        if isinstance(address, IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if "%" in str(address):
            raise ValueError
        return str(address)
    except (TypeError, ValueError):
        raise AppError("SERVICE_UNAVAILABLE") from None


@dataclass(frozen=True)
class InferenceIdentity:
    subject_id: UUID
    ip: str = field(repr=False)
    account_id: UUID | None = None

    def __post_init__(self):
        if not isinstance(self.subject_id, UUID) or self.account_id is not None and not isinstance(self.account_id, UUID):
            raise ValueError("인증된 주체 식별자가 필요합니다")
        object.__setattr__(self, "ip", normalize_ip(self.ip))


@dataclass(frozen=True)
class Lease:
    token: str = field(repr=False)


class AdmissionStore(Protocol):
    async def check_http(self, identities: list[str], member: str) -> None: ...
    async def acquire(self, budgets: list[str], token: str, kind: Kind, identity_key_id: str) -> Lease: ...
    async def release(self, lease: Lease) -> None: ...
    async def is_ready(self, identity_key_id: str) -> bool: ...


class UnavailableAdmissionStore:
    async def check_http(self, *args, **kwargs):
        raise AppError("SERVICE_UNAVAILABLE")

    acquire = release = check_http

    async def is_ready(self, identity_key_id):
        return False


class RuntimeCompletion:
    """현재 호출의 종료 또는 연결 미성립 확인. HTTP 취소 처리기에서 호출하면 안 된다."""

    def __init__(self):
        self.ended = False

    def confirm_ended(self) -> None:
        self.ended = True


class AdmissionService:
    def __init__(self, store: AdmissionStore, *, identity_key: bytes):
        if len(identity_key) != 32:
            raise ValueError("한도 식별키는 32바이트여야 합니다")
        self.store = store
        self._identity_key = identity_key
        self._identity_key_id = hashlib.sha256(identity_key).hexdigest()

    def digest(self, category: str, value: str) -> str:
        return hmac.new(self._identity_key, f"{category}:{value}".encode("ascii"), hashlib.sha256).hexdigest()

    @property
    def identity_key_id(self) -> str:
        return self._identity_key_id

    def generation_budget(self, identity: InferenceIdentity) -> str:
        if identity.account_id is not None:
            return self.digest("generation-account", str(identity.account_id))
        return self.digest("generation-ip", identity.ip)

    async def check_http(self, ip: str, subject_id: UUID | None = None) -> None:
        identities = [self.digest("ip", normalize_ip(ip))]
        if subject_id is not None:
            if not isinstance(subject_id, UUID):
                raise ValueError("주체 식별자 형식 오류")
            identities.append(self.digest("subject", str(subject_id)))
        await self.store.check_http(identities, secrets.token_hex(16))

    async def run(self, identity: InferenceIdentity, kind: Kind, operation: Callable[[RuntimeCompletion], Awaitable[T]], *, timeout_seconds: float = 60.0) -> T:
        if kind not in {"llm", "stt", "tts"} or not 0 < timeout_seconds <= 60:
            raise ValueError("추론 실행 종류/시간 범위 오류")
        if kind == "tts":
            budgets = [self.digest("tts-subject", str(identity.subject_id)), self.digest("tts-ip", identity.ip)]
        else:
            budgets = [self.generation_budget(identity)]
        lease = await self.store.acquire(budgets, secrets.token_hex(32), kind, self._identity_key_id)
        completion = RuntimeCompletion()
        try:
            # 취소/시간 초과 자체는 종료 증거가 아니다. 미확인 실행은 Redis 슬롯을 유지한다.
            return await asyncio.wait_for(operation(completion), timeout=timeout_seconds)
        except TimeoutError:
            raise AppError("AI_TIMEOUT") from None
        finally:
            if completion.ended:
                await self.store.release(lease)

    async def is_ready(self) -> bool:
        return await self.store.is_ready(self._identity_key_id)


class UnavailableAdmissionService:
    async def check_http(self, *args, **kwargs):
        raise AppError("SERVICE_UNAVAILABLE")

    run = check_http

    @property
    def identity_key_id(self):
        raise AppError("SERVICE_UNAVAILABLE")

    def generation_budget(self, identity):
        raise AppError("SERVICE_UNAVAILABLE")

    async def is_ready(self):
        return False
