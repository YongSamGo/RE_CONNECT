"""목적·현재 안내문·인증 주체를 검증한 뒤에만 동의를 기록한다.

주체는 인증 서비스가 만든 내부 입력이며 HTTP 본문으로 만들지 않는다.
읽기 검사는 실행 전 검사용이다. 결과 저장은 같은 트랜잭션/스크립트에서
철회·수명·삭제 세대를 다시 검사해야 한다(#27/#74/#78).
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from pydantic import TypeAdapter

from app.core.business_errors import AppError
from app.modules.consents.models import ConsentCreate, ConsentPurpose, ConsentState, NoticeVersion


@dataclass(frozen=True)
class ConsentActor:
    subject_id: UUID
    # None은 익명. 인증 완료 후 서버가 조회한 회원 ID만 넘긴다.
    member_id: UUID | None = None
    session_digest: str | None = None
    member_generation: int | None = None


class ConsentStoreUnavailable(Exception):
    pass


class ConsentSubjectExpired(Exception):
    pass


class ConsentVersionError(ValueError):
    pass


class ConsentStore(Protocol):
    async def grant(self, actor: ConsentActor, request: ConsentCreate) -> tuple[ConsentState, bool]: ...
    async def current(self, actor: ConsentActor, purpose: ConsentPurpose) -> ConsentState | None: ...


class UnavailableConsentStore:
    async def grant(self, *args, **kwargs):
        raise ConsentStoreUnavailable

    current = grant


class ConsentService:
    def __init__(self, store: ConsentStore, *, ai_version: str | None, storage_version: str | None):
        validator = TypeAdapter(NoticeVersion)
        self.versions = MappingProxyType({
            "ai_processing": validator.validate_python(ai_version) if ai_version is not None else None,
            "storage": validator.validate_python(storage_version) if storage_version is not None else None,
        })
        self.store = store

    async def grant(self, actor: ConsentActor, request: ConsentCreate) -> tuple[ConsentState, bool]:
        if request.purpose == "storage" and actor.member_id is None:
            raise AppError("UNAUTHENTICATED")
        version = self.versions[request.purpose]
        if version is None:
            # #9의 실제 운영 안내문이 확정되지 않았으면 예제 버전으로 대신 승인하지 않는다.
            raise AppError("SERVICE_UNAVAILABLE")
        if request.notice_version != version:
            raise ConsentVersionError("현재 안내문 버전이 아닙니다")
        try:
            result, created = await self.store.grant(actor, request)
        except ConsentStoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None
        except ConsentSubjectExpired:
            raise AppError("NOT_FOUND") from None
        return result, created

    async def current(self, actor: ConsentActor) -> list[ConsentState]:
        result = []
        try:
            for purpose, version in self.versions.items():
                if version is None or purpose == "storage" and actor.member_id is None:
                    continue
                state = await self.store.current(actor, purpose)
                if state is not None and state.notice_version == version:
                    result.append(state)
        except ConsentStoreUnavailable:
            raise AppError("SERVICE_UNAVAILABLE") from None
        except ConsentSubjectExpired:
            raise AppError("NOT_FOUND") from None
        return result

    async def require(self, actor: ConsentActor, purpose: ConsentPurpose, *, notice_version: str | None = None) -> ConsentState:
        if purpose not in self.versions:
            raise AppError("CONSENT_REQUIRED")
        if purpose == "storage" and actor.member_id is None:
            raise AppError("UNAUTHENTICATED")
        version = self.versions[purpose]
        if version is None or notice_version is not None and notice_version != version:
            raise AppError("CONSENT_REQUIRED")
        states = await self.current(actor)
        for state in states:
            if state.purpose == purpose:
                return state
        raise AppError("CONSENT_REQUIRED")

    async def bind_session(self, actor: ConsentActor, notice_version: str):
        if actor.member_id is None:
            return
        await self.require(actor, 'ai_processing', notice_version=notice_version)
        try:
            await self.store.bind_session(actor, notice_version)
        except (ConsentStoreUnavailable, ConsentSubjectExpired):
            raise AppError('SERVICE_UNAVAILABLE') from None
        await self.require(actor, 'ai_processing', notice_version=notice_version)
