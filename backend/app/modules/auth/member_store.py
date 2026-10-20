"""단일 Redis의 회원 결합·새 세션 교체·재인증. 계정 역할은 DB에서 읽는다."""

from dataclasses import dataclass
import re
from uuid import UUID

from redis.exceptions import RedisError

from app.modules.sessions.service import ABSOLUTE_MS, IDLE_MS, StoreUnavailable, parse_session


@dataclass(frozen=True)
class MemberBinding:
    user_id: UUID
    now_ms: int
    reauth_until_ms: int


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
local b = redis.call('HMGET', KEYS[1], 'user_id', 'reauth_until_ms')
if not b[1] then return {} end
local until_ms = tonumber(b[2] or '0')
if not until_ms or until_ms < 0 or until_ms > now + 300000 then return redis.error_reply('Invalid binding state') end
return {b[1], tostring(now), tostring(until_ms)}
"""

_SWITCH = _LIFETIME + """
if redis.call('EXISTS', KEYS[2]) == 1 then return {} end
-- 새 주체·CSRF·수명을 만들고 같은 원자 처리로 이전 세션을 폐기한다.
redis.call('HSET', KEYS[2], 'subject_id', ARGV[3], 'created_ms', now, 'last_ms', now, 'csrf_secret', ARGV[4])
redis.call('PEXPIRE', KEYS[2], tonumber(ARGV[2]))
if ARGV[5] ~= '' then
    redis.call('HSET', KEYS[2], 'user_id', ARGV[5], 'reauth_until_ms', 0)
end
redis.call('DEL', KEYS[1], KEYS[3])
return {ARGV[3], tostring(now), tostring(now), ARGV[4], tostring(now), ARGV[5]}
"""

_REAUTH = _LIFETIME + """
if redis.call('HGET', KEYS[1], 'user_id') ~= ARGV[3] then return {} end
local until_ms = now + math.min(300000, ttl)
redis.call('HSET', KEYS[1], 'reauth_until_ms', until_ms)
return {ARGV[3], tostring(now), tostring(until_ms)}
"""


class RedisMemberStore:
    def __init__(self, client, *, session_prefix="rc:session:v1:", flow_prefix="rc:oauth:v1:"):
        self.client, self.session_prefix, self.flow_prefix = client, session_prefix, flow_prefix
        self._read, self._switch, self._reauth = (client.register_script(v) for v in (_READ, _SWITCH, _REAUTH))

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
            uid, now, until = values
            return MemberBinding(UUID(uid), int(now), int(until))
        except (ValueError, TypeError):
            raise StoreUnavailable from None

    async def read(self, digest):
        try:
            return self._binding(await self._read(keys=[self.key(digest)], args=[ABSOLUTE_MS, IDLE_MS]))
        except RedisError:
            raise StoreUnavailable from None

    async def switch(self, old_digest, new_digest, subject_id, csrf_secret, user_id=None):
        try:
            keys = [self.key(old_digest), self.key(new_digest), self.flow_prefix + self._digest(old_digest)]
            values = await self._switch(keys=keys, args=[ABSOLUTE_MS, IDLE_MS, str(subject_id), csrf_secret,
                                                       str(user_id) if user_id is not None else ""])
            return parse_session(values, new_digest)
        except RedisError:
            raise StoreUnavailable from None

    async def reauth(self, digest, user_id):
        try:
            return self._binding(await self._reauth(keys=[self.key(digest)], args=[ABSOLUTE_MS, IDLE_MS, str(user_id)]))
        except RedisError:
            raise StoreUnavailable from None


class UnavailableMemberStore:
    async def read(self, *args):
        raise StoreUnavailable

    switch = read
    reauth = read
