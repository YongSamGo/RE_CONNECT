"""단일 Redis의 원자적 세션 생성/조회/교체. Lua 소스는 고정하고 인자는 분리한다."""

import re
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.modules.sessions.service import ABSOLUTE_MS, IDLE_MS, StoreUnavailable, parse_session

_CREATE = """
if redis.call('EXISTS', KEYS[1]) == 1 then return {} end
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
redis.call('HSET', KEYS[1], 'subject_id', ARGV[1], 'created_ms', now, 'last_ms', now, 'csrf_secret', ARGV[2])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[3]))
return {ARGV[1], tostring(now), tostring(now), ARGV[2], tostring(now)}
"""
_LOAD = """
local v = redis.call('HMGET', KEYS[1], 'subject_id', 'created_ms', 'last_ms', 'csrf_secret', 'user_id')
if not v[1] then return {} end
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local created, last = tonumber(v[2]), tonumber(v[3])
if not created or not last or last < created or now < created or now < last then return redis.error_reply('Invalid session state') end
if now >= created + tonumber(ARGV[2]) or now >= last + tonumber(ARGV[1]) then
    redis.call('DEL', KEYS[1]); return {}
end
if ARGV[3] == '1' then
    v[3] = tostring(now)
    redis.call('HSET', KEYS[1], 'last_ms', now)
    redis.call('PEXPIRE', KEYS[1], math.min(tonumber(ARGV[1]), created + tonumber(ARGV[2]) - now))
end
return {v[1], v[2], v[3], v[4], tostring(now), v[5] or ''}
"""
_ROTATE = """
if redis.call('HGET', KEYS[1], 'user_id') then return redis.error_reply('Authenticated transition required') end
local v = redis.call('HMGET', KEYS[1], 'subject_id', 'created_ms', 'last_ms', 'csrf_secret')
if not v[1] or redis.call('EXISTS', KEYS[2]) == 1 then return {} end
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local created, last = tonumber(v[2]), tonumber(v[3])
if not created or not last or last < created or now < created or now < last then return redis.error_reply('Invalid session state') end
local ttl = math.min(created + tonumber(ARGV[2]) - now, last + tonumber(ARGV[1]) - now)
if ttl <= 0 then redis.call('DEL', KEYS[1]); return {} end
redis.call('HSET', KEYS[2], 'subject_id', v[1], 'created_ms', v[2], 'last_ms', v[3], 'csrf_secret', ARGV[3])
redis.call('PEXPIRE', KEYS[2], ttl)
redis.call('DEL', KEYS[1])
return {v[1], v[2], v[3], ARGV[3], tostring(now)}
"""


class RedisSessionStore:
    def __init__(self, client: Redis, *, prefix: str = "rc:session:v1:"):
        self.client = client
        self.prefix = prefix
        self._create = client.register_script(_CREATE)
        self._load = client.register_script(_LOAD)
        self._rotate = client.register_script(_ROTATE)

    def key(self, digest: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise StoreUnavailable
        return self.prefix + digest

    @staticmethod
    def _parse(values, digest):
        return parse_session(values, digest)

    async def create(self, digest, subject_id, csrf_secret):
        try:
            values = await self._create(keys=[self.key(digest)], args=[str(subject_id), csrf_secret, IDLE_MS])
            return self._parse(values, digest)
        except RedisError:
            raise StoreUnavailable from None

    async def load(self, digest, *, touch):
        try:
            values = await self._load(keys=[self.key(digest)], args=[IDLE_MS, ABSOLUTE_MS, "1" if touch else "0"])
            return self._parse(values, digest)
        except RedisError:
            raise StoreUnavailable from None

    async def rotate(self, old_digest, new_digest, csrf_secret):
        try:
            values = await self._rotate(keys=[self.key(old_digest), self.key(new_digest)], args=[IDLE_MS, ABSOLUTE_MS, csrf_secret])
            return self._parse(values, new_digest)
        except RedisError:
            raise StoreUnavailable from None

    async def revoke(self, digest):
        try:
            await self.client.delete(self.key(digest))
        except RedisError:
            raise StoreUnavailable from None
