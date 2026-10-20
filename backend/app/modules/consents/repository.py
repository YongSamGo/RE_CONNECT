"""Redis 익명 세션의 동의와 SQL 회원 동의. 입력은 고정 SQL/Lua 인자로 전달한다."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DatabaseSession

from app.contracts.time import utc_now
from app.modules.consents.models import ConsentCreate, ConsentPurpose, ConsentState
from app.modules.consents.service import ConsentActor, ConsentStoreUnavailable, ConsentSubjectExpired
from app.modules.sessions.service import ABSOLUTE_MS, IDLE_MS
from app.persistence.members import Consent, User

# 동의는 세션 해시에 둬서 세션 삭제/만료 후 별도의 동의 키가 남지 않는다.
# 만료 확인과 쓰기를 한 스크립트로 묶으며 읽기·동의 자체로 TTL을 연장하지 않는다.
_CONSENT = """
local v = redis.call('HMGET', KEYS[1], 'subject_id', 'created_ms', 'last_ms')
if not v[1] or v[1] ~= ARGV[1] then return {} end
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local created, last = tonumber(v[2]), tonumber(v[3])
if not created or not last or last < created or now < last then
    return redis.error_reply('Invalid session state')
end
if now >= created + tonumber(ARGV[2]) or now >= last + tonumber(ARGV[3]) then
    redis.call('DEL', KEYS[1]); return {}
end
local c = redis.call('HMGET', KEYS[1], 'ai_notice_version', 'ai_granted_ms')
if c[1] or c[2] then
    local granted = tonumber(c[2])
    if not c[1] or not granted or granted < created or granted > now then
        return redis.error_reply('Invalid consent state')
    end
end
if ARGV[4] == 'read' then
    if not c[1] and not c[2] then return {'absent'} end
    if not c[1] or not c[2] then return redis.error_reply('Invalid consent state') end
    return {'existing', c[1], c[2]}
end
if c[1] == ARGV[5] and c[2] then return {'existing', c[1], c[2]} end
redis.call('HSET', KEYS[1], 'ai_notice_version', ARGV[5], 'ai_granted_ms', now)
return {'created', ARGV[5], tostring(now)}
"""


class RedisConsentStore:
    def __init__(self, client, *, session_key: Callable[[str], str]):
        self._script = client.register_script(_CONSENT)
        self._session_key = session_key

    async def _execute(self, actor, *, version=None):
        if actor.member_id is not None or actor.session_digest is None:
            raise ConsentSubjectExpired
        try:
            values = await self._script(
                keys=[self._session_key(actor.session_digest)],
                args=[str(actor.subject_id), ABSOLUTE_MS, IDLE_MS, "grant" if version is not None else "read", version or ""],
            )
            if not values:
                raise ConsentSubjectExpired
            if values == ["absent"]:
                return None, False
            status, stored_version, timestamp = values
            if status not in ("existing", "created"):
                raise ValueError
            state = ConsentState(purpose="ai_processing", notice_version=stored_version,
                                 granted_at=datetime.fromtimestamp(int(timestamp) / 1000, UTC))
            return state, status == "created"
        except (RedisError, ValueError, TypeError, OverflowError, OSError, ValidationError):
            raise ConsentStoreUnavailable from None

    async def grant(self, actor: ConsentActor, request: ConsentCreate):
        if request.purpose != "ai_processing":
            raise ConsentSubjectExpired
        return await self._execute(actor, version=request.notice_version)

    async def current(self, actor: ConsentActor, purpose: ConsentPurpose):
        if purpose != "ai_processing":
            return None
        state, _ = await self._execute(actor)
        return state


class SQLConsentStore:
    def __init__(self, engine):
        self.engine = engine

    @staticmethod
    def _owner(db, actor):
        if actor.member_id is None:
            raise ConsentSubjectExpired
        owner = db.scalar(select(User).where(User.id == actor.member_id).with_for_update())
        if owner is None or owner.status != "active":
            raise ConsentSubjectExpired
        return owner

    @staticmethod
    def _latest(db, owner_id, purpose):
        # 철회 전 기록을 되살리지 않도록 최신 수락 기록 하나만 검사한다.
        return db.scalar(select(Consent).where(Consent.owner_id == owner_id, Consent.purpose == purpose)
                         .order_by(Consent.accepted_at.desc(), Consent.id.desc()).limit(1))

    @staticmethod
    def _state(row):
        return ConsentState(purpose=row.purpose, notice_version=row.notice_version, granted_at=row.accepted_at)

    def _grant(self, actor, request):
        try:
            with DatabaseSession(self.engine) as db, db.begin():
                self._owner(db, actor)
                row = self._latest(db, actor.member_id, request.purpose)
                if row is not None and row.withdrawn_at is None and row.notice_version == request.notice_version:
                    return self._state(row), False
                row = Consent(owner_id=actor.member_id, purpose=request.purpose,
                              notice_version=request.notice_version, accepted_at=utc_now(), withdrawn_at=None)
                db.add(row)
                db.flush()
                return self._state(row), True
        except (SQLAlchemyError, ValidationError):
            raise ConsentStoreUnavailable from None

    async def grant(self, actor, request):
        return await asyncio.to_thread(self._grant, actor, request)

    def _current(self, actor, purpose):
        try:
            with DatabaseSession(self.engine) as db, db.begin():
                self._owner(db, actor)
                row = self._latest(db, actor.member_id, purpose)
                return self._state(row) if row is not None and row.withdrawn_at is None else None
        except (SQLAlchemyError, ValidationError):
            raise ConsentStoreUnavailable from None

    async def current(self, actor, purpose):
        return await asyncio.to_thread(self._current, actor, purpose)


class RoutedConsentStore:
    def __init__(self, anonymous, member):
        self.anonymous = anonymous
        self.member = member

    def _store(self, actor):
        return self.member if actor.member_id is not None else self.anonymous

    async def grant(self, actor, request):
        return await self._store(actor).grant(actor, request)

    async def current(self, actor, purpose):
        return await self._store(actor).current(actor, purpose)
