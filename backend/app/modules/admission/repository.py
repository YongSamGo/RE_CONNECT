"""KST 일일 집계와 슬롯을 같은 비만료 제어 해시에 둔다. 유실 시 자동 초기화 금지."""

import re
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.business_errors import AppError
from app.modules.admission.service import Lease

_HTTP = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local retry = 0
for _, key in ipairs(KEYS) do
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now - 60000)
    if redis.call('ZCARD', key) >= 60 then
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        retry = math.max(retry, math.ceil((tonumber(oldest[2]) + 60000 - now) / 1000))
    end
end
if retry > 0 then return {'RATE_LIMITED', tostring(retry)} end
for _, key in ipairs(KEYS) do
    redis.call('ZADD', key, now, ARGV[1])
    redis.call('PEXPIRE', key, 60000)
end
return {'ok'}
"""

_ACQUIRE = """
local v = redis.call('HMGET', KEYS[1], 'epoch', 'day', 'global', 'active')
if v[1] ~= ARGV[1] or redis.call('PTTL', KEYS[1]) ~= -1 then return {'SERVICE_UNAVAILABLE'} end
if redis.call('HGET', KEYS[1], 'key_id') ~= ARGV[4] then return {'SERVICE_UNAVAILABLE'} end
if not v[2] or not string.match(v[2], '^%d+$') or not v[3] or not string.match(v[3], '^%d+$') then return {'SERVICE_UNAVAILABLE'} end
local t = redis.call('TIME')
local day = math.floor((tonumber(t[1]) + 32400) / 86400)
local retry = (day + 1) * 86400 - 32400 - tonumber(t[1])
if tonumber(v[2]) > day then return {'SERVICE_UNAVAILABLE'} end
if tonumber(v[2]) < day then
    -- 한 날에 최대 500개 실행: 과거 일별 식별자 필드도 유한한 크기로 정리한다.
    for _, field in ipairs(redis.call('HKEYS', KEYS[1])) do
        if string.sub(field, 1, 6) == 'limit:' then redis.call('HDEL', KEYS[1], field) end
    end
    redis.call('HSET', KEYS[1], 'day', tostring(day), 'global', '0')
    v[3] = '0'
end
if tonumber(v[3]) >= 500 then return {'DAILY_QUOTA_EXCEEDED', tostring(retry)} end
for i = 5, #ARGV do
    local count = redis.call('HGET', KEYS[1], 'limit:' .. ARGV[i])
    if count and not string.match(count, '^%d+$') then return {'SERVICE_UNAVAILABLE'} end
    if count and tonumber(count) >= 60 then return {'DAILY_QUOTA_EXCEEDED', tostring(retry)} end
end
if v[4] then return {'INFERENCE_BUSY', '2'} end
redis.call('HINCRBY', KEYS[1], 'global', 1)
for i = 5, #ARGV do redis.call('HINCRBY', KEYS[1], 'limit:' .. ARGV[i], 1) end
redis.call('HSET', KEYS[1], 'active', ARGV[2], 'kind', ARGV[3])
return {'ok'}
"""

_RELEASE = """
local v = redis.call('HMGET', KEYS[1], 'epoch', 'active')
if v[1] ~= ARGV[1] or redis.call('PTTL', KEYS[1]) ~= -1 then return {'SERVICE_UNAVAILABLE'} end
if v[2] ~= ARGV[2] then return {'SERVICE_UNAVAILABLE'} end
redis.call('HDEL', KEYS[1], 'active', 'kind')
return {'ok'}
"""


class RedisAdmissionStore:
    def __init__(self, client: Redis, *, epoch: UUID, prefix: str = "rc:admission:v1:"):
        self.client = client
        self.epoch = epoch
        self.prefix = prefix
        self.control_key = prefix + "control"
        self._http = client.register_script(_HTTP)
        self._acquire = client.register_script(_ACQUIRE)
        self._release = client.register_script(_RELEASE)

    async def _call(self, script, keys, args):
        try:
            values = await script(keys=keys, args=args)
        except RedisError:
            raise AppError("SERVICE_UNAVAILABLE") from None
        if not isinstance(values, list) or not values:
            raise AppError("SERVICE_UNAVAILABLE")
        if values[0] == "SERVICE_UNAVAILABLE":
            raise AppError("SERVICE_UNAVAILABLE")
        if values[0] in {"RATE_LIMITED", "DAILY_QUOTA_EXCEEDED", "INFERENCE_BUSY"}:
            try:
                retry = int(values[1])
                if not 1 <= retry <= 86400:
                    raise ValueError
            except (ValueError, TypeError, IndexError):
                raise AppError("SERVICE_UNAVAILABLE") from None
            raise AppError(values[0], retry_after=retry)
        if values != ["ok"]:
            raise AppError("SERVICE_UNAVAILABLE")

    @staticmethod
    def _digests(values):
        if not 1 <= len(values) <= 2 or len(set(values)) != len(values) or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in values):
            raise ValueError("한도 식별자 형식 오류")

    async def check_http(self, identities, member):
        self._digests(identities)
        await self._call(self._http, [self.prefix + "http:" + value for value in identities], [member])

    async def acquire(self, budgets, token, kind, identity_key_id):
        self._digests(budgets)
        await self._call(self._acquire, [self.control_key], [str(self.epoch), token, kind, identity_key_id, *budgets])
        return Lease(token)

    async def release(self, lease):
        await self._call(self._release, [self.control_key], [str(self.epoch), lease.token])

    async def is_ready(self, identity_key_id):
        try:
            epoch, key_id, day, count = await self.client.hmget(self.control_key, "epoch", "key_id", "day", "global")
            return epoch == str(self.epoch) and key_id == identity_key_id and day is not None and day.isdigit() and count is not None and count.isdigit() and await self.client.pttl(self.control_key) == -1
        except RedisError:
            return False
