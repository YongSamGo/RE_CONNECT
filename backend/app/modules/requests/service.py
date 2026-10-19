"""W03-05. 실행 권한과 결과 참조만 보관하며 업무 본문은 저장하지 않는다."""

from dataclasses import dataclass, field
import hashlib
import json
import re
import secrets
from typing import Literal, Protocol
from uuid import UUID

from app.core.business_errors import AppError

RETENTION_MS = 24 * 60 * 60 * 1000
RESOURCE_MAX_MS = 2 * 60 * 60 * 1000
MAX_REVISION = 2**31 - 1


@dataclass(frozen=True)
class RequestScope:
    subject_id: UUID
    api: str
    resource_id: UUID | None = None

    def __post_init__(self):
        if not isinstance(self.subject_id, UUID) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}", self.api):
            raise ValueError("서버가 정한 요청 범위가 필요합니다")
        if self.resource_id is not None and not isinstance(self.resource_id, UUID):
            raise ValueError("자원 식별자 형식 오류")


@dataclass(frozen=True)
class ResultReference:
    kind: Literal["profile", "draft", "transcription", "message", "report", "save_intent"]
    id: UUID
    version: int

    def __post_init__(self):
        if self.kind not in {"profile", "draft", "transcription", "message", "report", "save_intent"}:
            raise ValueError("정의되지 않은 결과 참조")
        if not isinstance(self.id, UUID) or type(self.version) is not int or not 1 <= self.version <= MAX_REVISION:
            raise ValueError("결과 참조 형식 오류")


@dataclass(frozen=True)
class Permit:
    scope: RequestScope
    key_id: UUID
    input_hash: str = field(repr=False)
    execution_id: str = field(repr=False)
    base_revision: int | None = None


@dataclass(frozen=True)
class Replay:
    result: ResultReference


class RequestStore(Protocol):
    async def begin(self, permit: Permit) -> Permit | Replay: ...
    async def complete(self, permit: Permit, result: ResultReference | None) -> None: ...
    async def create_resource(self, subject_id: UUID, resource_id: UUID, ttl_ms: int) -> bool: ...
    async def delete_resource(self, subject_id: UUID, resource_id: UUID) -> None: ...


class UnavailableRequestStore:
    async def begin(self, *args, **kwargs):
        raise AppError("SERVICE_UNAVAILABLE")

    complete = create_resource = delete_resource = begin


def input_fingerprint(validated_input: dict) -> str:
    """검증된 요청 모델의 JSON dump(대상 참조·기준 버전 포함)를 받는다.

    해시를 익명화로 간주하지 않는다. 원문을 반환하거나 로그에 기록하지 않는다.
    업로드는 검증한 파일의 SHA-256을 이 객체의 명시적 필드로 포함한다.
    """
    try:
        if type(validated_input) is not dict:
            raise ValueError
        encoded = json.dumps(validated_input, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > 65536:
            raise ValueError
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise AppError("VALIDATION_FAILED") from None
    return hashlib.sha256(encoded).hexdigest()


class RequestService:
    def __init__(self, store: RequestStore):
        self.store = store

    async def begin(self, scope: RequestScope, key: str, validated_input: dict, *, base_revision: int | None = None) -> Permit | Replay:
        try:
            # OpenAPI §IdempotencyKey: UUID. 중복 헤더는 HTTP 경계에서 거절한다.
            key_id = UUID(key)
            if str(key_id) != key.lower():
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AppError("VALIDATION_FAILED") from None
        if scope.resource_id is None:
            if base_revision is not None:
                raise AppError("VALIDATION_FAILED")
        elif type(base_revision) is not int or not 0 <= base_revision < MAX_REVISION:
            raise AppError("VALIDATION_FAILED")
        # 기준 리비전도 입력 정체성의 일부다. 본문과 별도 인자 사이 불일치를 막는다.
        digest = input_fingerprint({"input": validated_input, "base_revision": base_revision})
        return await self.store.begin(Permit(scope, key_id, digest, secrets.token_hex(32), base_revision))

    async def complete(self, permit: Permit, result: ResultReference | None) -> None:
        await self.store.complete(permit, result)

    async def create_resource(self, subject_id: UUID, resource_id: UUID, *, ttl_ms: int) -> bool:
        if not isinstance(subject_id, UUID) or not isinstance(resource_id, UUID) or type(ttl_ms) is not int or not 1 <= ttl_ms <= RESOURCE_MAX_MS:
            raise ValueError("임시 자원 수명 범위 오류")
        return await self.store.create_resource(subject_id, resource_id, ttl_ms)

    async def delete_resource(self, subject_id: UUID, resource_id: UUID) -> None:
        if not isinstance(subject_id, UUID) or not isinstance(resource_id, UUID):
            raise ValueError("자원 식별자 형식 오류")
        await self.store.delete_resource(subject_id, resource_id)


class SaveOnce(Protocol):
    """영구 저장 구현의 경계. 이 구현은 Redis complete로 대신할 수 없다.

    DB 트랜잭션 안에서 (account, API, key)의 UNIQUE 저널·입력 해시 검사,
    base_version CAS, 암호화 저장본 생성·결과 참조 기록을 함께 커밋해야 한다.
    커밋 응답 유실 후에는 같은 저널 결과를 재조회한다. 연결 구현은 #75/#76.
    """

    async def save_once(self, *, account_id: UUID, api: str, key_id: UUID, input_hash: str, base_version: int, approved_reference: ResultReference) -> ResultReference: ...
