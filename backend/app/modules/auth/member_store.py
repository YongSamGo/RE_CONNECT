"""단일 Redis의 회원 결합·새 세션 교체·재인증. 계정 역할은 DB에서 읽는다."""

from dataclasses import dataclass
import re
from uuid import UUID

from redis.exceptions import RedisError
from app.adapters.session_transition import _CLEANUP_PLAN, _CLEANUP_COMMIT

from app.modules.sessions.service import ABSOLUTE_MS, IDLE_MS, StoreUnavailable, parse_session
from app.modules.auth.member_cleanup import RedisMemberCleanup


MFA_MS = 60 * 60 * 1000


@dataclass(frozen=True)
class MemberBinding:
    user_id: UUID
    now_ms: int
    reauth_until_ms: int
    generation: int
    # 이 세션에서만 유효한 운영자 MFA 확인. 세션 교체 시 복사하지 않는다.
    mfa_until_ms: int = 0
    mfa_credential: UUID | None = None


_LIFETIME = """
local t = redis.call('TIME')
local now = tonumber(t[1])*1000 + math.floor(tonumber(t[2])/1000)
local s = redis.call('HMGET', KEYS[1], 'subject_id', 'created_ms', 'last_ms')
if not s[1] then return {} end
local created, last = tonumber(s[2]), tonumber(s[3])
if not created or not last or created > last or now < last then return redis.error_reply('Invalid session state') end
local ttl = math.min(created + tonumber(ARGV[1]) - now, last + tonumber(ARGV[2]) - now)
if ttl <= 0 or redis.call('PTTL', KEYS[1]) <= 0 then return {} end
"""

_READ = _LIFETIME + """
local b = redis.call('HMGET', KEYS[1], 'user_id', 'reauth_until_ms', 'user_generation', 'mfa_until_ms', 'mfa_credential')
if not b[1] or not b[3] then return {} end
if redis.call('SISMEMBER', ARGV[3] .. b[1] .. ':sessions', ARGV[4]) ~= 1 then return {} end
local until_ms = tonumber(b[2] or '0')
if not until_ms or until_ms < 0 or until_ms > now + 300000 then return redis.error_reply('Invalid binding state') end
local mfa_ms = tonumber(b[4] or '0')
if not mfa_ms or mfa_ms < 0 or mfa_ms > now + tonumber(ARGV[5]) then return redis.error_reply('Invalid binding state') end
return {b[1], tostring(now), tostring(until_ms), b[3], tostring(mfa_ms), b[5] or ''}
"""

_SWITCH = _LIFETIME + _CLEANUP_PLAN + """
if redis.call('EXISTS', KEYS[2]) == 1 then return {} end
if (redis.call('HGET', KEYS[1], 'user_id') or '') ~= ARGV[9] then return {} end
if ARGV[5] ~= '' then
    if redis.call('SCARD', KEYS[7]) > 16 then return redis.error_reply('Invalid member index') end
    for _, digest in ipairs(redis.call('SMEMBERS', KEYS[7])) do
        if redis.call('EXISTS', ARGV[10] .. digest, ARGV[10] .. digest .. ':journeys',
            ARGV[10] .. digest .. ':save-intent', ARGV[12] .. digest) == 0 then redis.call('SREM', KEYS[7], digest) end
    end
    local count = redis.call('SCARD', KEYS[7])
    if ARGV[9] == ARGV[5] and redis.call('SISMEMBER', KEYS[7], ARGV[7]) == 1 then count = count - 1 end
    if count >= 16 then return redis.error_reply('Member session limit') end
end
local pending = nil
if ARGV[6] ~= '' then
    pending = redis.call('HGETALL', KEYS[4])
    local expires = tonumber(redis.call('HGET', KEYS[4], 'expires_ms'))
    if redis.call('HGET', KEYS[1], 'user_id') or ARGV[5] == '' then return {} end
    if redis.call('HGET', KEYS[4], 'id') ~= ARGV[6] or not expires or expires <= now
        or redis.call('PTTL', KEYS[4]) <= 0 or redis.call('HGET', KEYS[4], 'subject_id') ~= s[1]
        or redis.call('HGET', KEYS[4], 'user_id') ~= '' then return {} end
    if redis.call('EXISTS', KEYS[5]) == 1 then return {} end
end
-- 새 주체·CSRF·수명을 만들고 같은 원자 처리로 이전 세션을 폐기한다.
redis.call('HSET', KEYS[2], 'subject_id', ARGV[3], 'created_ms', now, 'last_ms', now, 'csrf_secret', ARGV[4])
redis.call('PEXPIRE', KEYS[2], tonumber(ARGV[2]))
if ARGV[5] ~= '' then
    redis.call('HSET', KEYS[2], 'user_id', ARGV[5], 'reauth_until_ms', 0, 'user_generation', ARGV[8])
    redis.call('SADD', KEYS[7], ARGV[11])
    redis.call('PEXPIRE', KEYS[7], tonumber(ARGV[2]))
end
if pending then
    for i=1,#pending,2 do redis.call('HSET', KEYS[5], pending[i], pending[i+1]) end
    redis.call('HSET', KEYS[5], 'subject_id', ARGV[3], 'user_id', ARGV[5])
    redis.call('PEXPIREAT', KEYS[5], redis.call('HGET', KEYS[4], 'expires_ms'))
end
redis.call('DEL', KEYS[4])
""" + _CLEANUP_COMMIT + """
redis.call('DEL', KEYS[1], KEYS[3])
if ARGV[9] ~= '' then redis.call('SREM', KEYS[8], ARGV[7]) end
return {ARGV[3], tostring(now), tostring(now), ARGV[4], tostring(now), ARGV[5], tostring(cleaned_journeys)}
"""

# 같은 회원·세대·회원 색인에 있는 세션에만 MFA 확인을 기록한다. 세션 절대 만료를 넘기지 않는다.
_MFA = _LIFETIME + """
local b = redis.call('HMGET', KEYS[1], 'user_id', 'user_generation')
if b[1] ~= ARGV[3] or b[2] ~= ARGV[4] then return {} end
if redis.call('SISMEMBER', ARGV[6] .. ARGV[3] .. ':sessions', ARGV[7]) ~= 1 then return {} end
local until_ms = now + math.min(tonumber(ARGV[8]), created + tonumber(ARGV[1]) - now)
redis.call('HSET', KEYS[1], 'mfa_until_ms', until_ms, 'mfa_credential', ARGV[5])
return {tostring(until_ms)}
"""

_REAUTH = _LIFETIME + """
if redis.call('HGET', KEYS[1], 'user_id') ~= ARGV[3] then return {} end
local until_ms = now + math.min(300000, ttl)
redis.call('HSET', KEYS[1], 'reauth_until_ms', until_ms)
return {ARGV[3], tostring(now), tostring(until_ms), redis.call('HGET', KEYS[1], 'user_generation') or ''}
"""


class RedisMemberStore:
    def __init__(self, client, *, session_prefix="rc:session:v1:", flow_prefix="rc:oauth:v1:"):
        self.client, self.session_prefix, self.flow_prefix = client, session_prefix, flow_prefix
        self.member_prefix = session_prefix + 'member:'
        self._read, self._switch, self._reauth, self._mfa = (client.register_script(v) for v in (_READ, _SWITCH, _REAUTH, _MFA))

    @staticmethod
    def _digest(digest):
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise StoreUnavailable
        return digest

    def key(self, digest):
        digest = self._digest(digest)
        return self.session_prefix + digest

    @staticmethod
    def _binding(values):
        if not values:
            return None
        try:
            uid, now, until, generation, *mfa = values
            generation = int(generation)
            if not 0 <= generation < 2147483647 or len(mfa) not in (0, 2): raise ValueError
            mfa_until, credential = (int(mfa[0]), UUID(mfa[1]) if mfa[1] else None) if mfa else (0, None)
            if mfa_until < 0 or (mfa_until > 0) != (credential is not None): raise ValueError
            return MemberBinding(UUID(uid), int(now), int(until), generation, mfa_until, credential)
        except (ValueError, TypeError):
            raise StoreUnavailable from None

    async def read(self, digest):
        try:
            return self._binding(await self._read(keys=[self.key(digest)], args=[ABSOLUTE_MS, IDLE_MS, self.member_prefix, digest, MFA_MS]))
        except RedisError:
            raise StoreUnavailable from None

    async def switch(self, old_digest, new_digest, subject_id, csrf_secret, user_id=None, *, save_intent_id=None, generation=0, old_user_id=None, with_counts=False):
        if type(generation) is not int or not 0 <= generation < 2147483647: raise StoreUnavailable
        try:
            if user_id is not None:
                index = self.member_prefix + str(user_id) + ':sessions'
                if await self.client.scard(index) > 16: raise StoreUnavailable
                digests = await self.client.smembers(index)
                if len(digests) > 16: raise StoreUnavailable
                for digest in digests:
                    if not await self.client.exists(self.key(digest)):
                        await RedisMemberCleanup(self).revoke_one(user_id, digest)
            keys = [self.key(old_digest), self.key(new_digest), self.flow_prefix + self._digest(old_digest)]
            keys += [self.key(old_digest) + ':save-intent', self.key(new_digest) + ':save-intent', self.key(old_digest) + ':journeys']
            keys += [self.member_prefix + str(user_id) + ':sessions', self.member_prefix + str(old_user_id) + ':sessions']
            values = await self._switch(keys=keys, args=[ABSOLUTE_MS, IDLE_MS, str(subject_id), csrf_secret,
                                                       str(user_id) if user_id is not None else "",
                                                       str(save_intent_id) if save_intent_id else '', old_digest, generation,
                                                       str(old_user_id) if old_user_id else '', self.session_prefix, new_digest, self.flow_prefix])
            session = parse_session([*values[:6], str(generation) if user_id else ''] if values else [], new_digest)
            return (session, int(values[6]) if values else 0) if with_counts else session
        except RedisError:
            raise StoreUnavailable from None

    async def reauth(self, digest, user_id):
        try:
            return self._binding(await self._reauth(keys=[self.key(digest)], args=[ABSOLUTE_MS, IDLE_MS, str(user_id)]))
        except RedisError:
            raise StoreUnavailable from None

    async def mark_mfa(self, digest, user_id, generation, credential_id):
        """MFA 만료 시각(ms). 세션이 바뀌었거나 다른 회원·세대면 None."""
        if type(generation) is not int or not 0 <= generation < 2147483647 or not isinstance(credential_id, UUID):
            raise StoreUnavailable
        try:
            values = await self._mfa(keys=[self.key(digest)], args=[ABSOLUTE_MS, IDLE_MS, str(user_id), str(generation),
                                                                   str(credential_id), self.member_prefix, digest, MFA_MS])
        except RedisError:
            raise StoreUnavailable from None
        if not values:
            return None
        try:
            return int(values[0])
        except (TypeError, ValueError):
            raise StoreUnavailable from None

    async def discard(self, session):
        await RedisMemberCleanup(self).revoke_one(session.user_id, session.digest)


class UnavailableMemberStore:
    async def read(self, *args, **kwargs):
        raise StoreUnavailable

    switch = read
    reauth = read
    mark_mfa = read
    discard = read
