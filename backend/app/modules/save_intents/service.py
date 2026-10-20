"""승인본의 일회 전달. 인증 성공과 자료 저장 성공을 구분한다."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError

from app.contracts.drafts import JourneyDraft
from app.contracts.profile import ProfileContent
from app.contracts.save_intents import PendingSaveIntent
from app.core.business_errors import AppError
from app.modules.requests.service import input_fingerprint


@dataclass(frozen=True)
class ApprovedTransfer:
    profile: ProfileContent = field(repr=False)
    confirmed_at: datetime
    draft: JourneyDraft | None = field(repr=False)


class SaveIntentService:
    session_transition_managed = True

    def __init__(self, store, members, consents, policy):
        self.store, self.members, self.consents, self.policy = store, members, consents, policy

    async def create(self, session, key, body):
        if session.user_id is not None:
            await self.members.require(session)
            raise AppError('ALREADY_SIGNED_IN')
        if body.profile is None:
            raise AppError('VALIDATION_FAILED')
        try:
            identity = UUID(key)
            if str(identity) != key.lower():
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AppError('VALIDATION_FAILED') from None
        return await self.store.create(session, identity, input_fingerprint(body.model_dump(mode='json')), body)

    async def reference(self, session):
        if session.user_id is not None:
            return None
        pending = await self.store.pending(session)
        return str(pending.save_intent_id) if pending is not None else None

    async def pending(self, session, account):
        pending = await self.store.pending(session, account.id)
        if pending is None:
            return None
        version = await self.policy.current_version(account.id)
        return PendingSaveIntent(**pending.model_dump(), existing_saved_profile_version=version)

    async def drain(self, session):
        if session.user_id is not None:
            await self.policy.barrier(session.user_id)

    async def take_approved(self, session, account, identity, *, allow_draft=True):
        if not allow_draft:
            pending = await self.store.pending(session, account.id, expected=identity)
            if pending is None:
                raise AppError('SAVE_INTENT_NOT_FOUND')
            if pending.targets.draft:
                raise AppError('INVALID_STATE_TRANSITION')
        raw = await self.store.take(session, account.id, identity)
        try:
            profile = ProfileContent.model_validate_json(raw['profile'])
            draft = JourneyDraft.model_validate_json(raw['draft']) if raw['draft'] else None
            approved = ApprovedTransfer(profile, datetime.fromtimestamp(int(raw['confirmed_ms']) / 1000, UTC), draft)
            if draft is not None and (draft.approved_at is None or draft.review_reasons or not allow_draft):
                raise ValueError
            return approved
        except (ValidationError, ValueError, TypeError, KeyError, OverflowError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def consume(self, session, identity, *, storage_notice_version, base_saved_version, write):
        """#75/#76 소비자는 이 경계 안의 SQL 트랜잭션으로만 실제 저장한다.

        일회 소비 후 SQL 실패 시 저장 대기는 복구하지 않는다. 다시 확인/발급해야 한다.
        성공한 저장을 재전송하는 멱등성은 소비자의 SQL 기록으로 보장해야 한다.
        """
        account = await self.members.require(session)
        if base_saved_version is not None and (type(base_saved_version) is not int or base_saved_version < 1):
            raise AppError('VALIDATION_FAILED')
        current = self.consents.versions['storage']
        if current is None or storage_notice_version != current:
            raise AppError('CONSENT_REQUIRED')
        async with self.policy.authorize(account.id, current, base_saved_version) as db:
            approved = await self.take_approved(session, account, identity)
            # 대기/SQL 잠금 중 회수를 다시 검사한다. 실제 writer도 현재 버전·소유권을 검사한다.
            await self.members.require(session)
            result = await write(db, account, approved)
            await self.members.require(session)
            return result
