"""KST 일일 집계와 슬롯을 같은 비만료 제어 해시에 둔다. 유실 시 자동 초기화 금지(운영자 `initialize`만)."""

from dataclasses import dataclass
import hashlib
import hmac
import re
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.business_errors import AppError
from app.modules.admission.service import GLOBAL_DAILY_LIMIT, Lease

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
    -- 한 날에 실행 수가 전체 한도로 묶인다: 과거 일별 식별자 필드도 유한한 크기로 정리한다.
    for _, field in ipairs(redis.call('HKEYS', KEYS[1])) do
        if string.sub(field, 1, 6) == 'limit:' then redis.call('HDEL', KEYS[1], field) end
    end
    redis.call('HSET', KEYS[1], 'day', tostring(day), 'global', '0')
    v[3] = '0'
end
if tonumber(v[3]) >= __GLOBAL_DAILY_LIMIT__ then return {'DAILY_QUOTA_EXCEEDED', tostring(retry)} end
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
""".replace("__GLOBAL_DAILY_LIMIT__", str(GLOBAL_DAILY_LIMIT))

_RELEASE = """
local v = redis.call('HMGET', KEYS[1], 'epoch', 'active')
if v[1] ~= ARGV[1] or redis.call('PTTL', KEYS[1]) ~= -1 then return {'SERVICE_UNAVAILABLE'} end
if v[2] ~= ARGV[2] then return {'SERVICE_UNAVAILABLE'} end
redis.call('HDEL', KEYS[1], 'active', 'kind')
return {'ok'}
"""


# 운영자 복구 전용. 세대·식별키가 맞고 지정한 lease가 아직 그대로일 때만 슬롯을 비운다.
# 일일 집계(`day`, `global`, `limit:*`)는 건드리지 않는다.
_RECOVER = """
local v = redis.call('HMGET', KEYS[1], 'epoch', 'key_id', 'active')
if v[1] ~= ARGV[1] or v[2] ~= ARGV[2] or redis.call('PTTL', KEYS[1]) ~= -1 then return {'SERVICE_UNAVAILABLE'} end
if not v[3] then return {'NOT_ACTIVE'} end
if v[3] ~= ARGV[3] then return {'LEASE_CHANGED'} end
redis.call('HDEL', KEYS[1], 'active', 'kind')
return {'ok'}
"""


# 운영자 초기화 전용. 제어 해시가 없을 때만 만들고, 있으면 어떤 필드도 바꾸지 않는다.
# ARGV[3]은 오늘 이미 쓴 것으로 칠 전역 집계다. 실행 기록이 없음을 확인했을 때만 0, 아니면 한도 값.
_INITIALIZE = """
if redis.call('EXISTS', KEYS[1]) == 1 then return {'EXISTS'} end
local t = redis.call('TIME')
local day = math.floor((tonumber(t[1]) + 32400) / 86400)
redis.call('HSET', KEYS[1], 'epoch', ARGV[1], 'key_id', ARGV[2], 'day', tostring(day), 'global', ARGV[3])
if tonumber(ARGV[3]) > 0 then redis.call('HSET', KEYS[1], 'recovery_day', tostring(day)) end
return {'ok'}
"""


def lease_fingerprint(token: str) -> str:
    """운영자 화면용 lease 지문. 원 token을 출력하지 않는다."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()[:16]


@dataclass(frozen=True)
class SlotStatus:
    ready: bool
    day: int | None
    global_count: int | None
    kind: str | None
    lease: str | None


class RedisAdmissionStore:
    def __init__(self, client: Redis, *, epoch: UUID, prefix: str = "rc:admission:v1:"):
        self.client = client
        self.epoch = epoch
        self.prefix = prefix
        self.control_key = prefix + "control"
        self._http = client.register_script(_HTTP)
        self._acquire = client.register_script(_ACQUIRE)
        self._release = client.register_script(_RELEASE)
        self._recover = client.register_script(_RECOVER)
        self._initialize = client.register_script(_INITIALIZE)

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

    async def slot_status(self, identity_key_id) -> SlotStatus:
        """운영자 확인용. 세대·키·집계 형식과 현재 슬롯 점유 여부만 돌려준다."""
        try:
            day, count, kind, active = await self.client.hmget(self.control_key, "day", "global", "kind", "active")
            ready = await self.is_ready(identity_key_id)
        except RedisError:
            raise AppError("SERVICE_UNAVAILABLE") from None
        return SlotStatus(
            ready=ready,
            day=int(day) if day is not None and day.isdigit() else None,
            global_count=int(count) if count is not None and count.isdigit() else None,
            kind=kind if kind in {"llm", "stt", "tts"} else None,
            lease=lease_fingerprint(active) if active is not None and active.isascii() else None,
        )

    async def recover(self, identity_key_id, fingerprint) -> str:
        """모든 런타임 정지를 운영자가 확인한 뒤 호출한다. 지정한 lease가 바뀌었으면 비우지 않는다."""
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{16}", fingerprint):
            raise ValueError("lease 지문 형식 오류")
        if not isinstance(identity_key_id, str) or not re.fullmatch(r"[0-9a-f]{64}", identity_key_id):
            raise ValueError("식별키 지문 형식 오류")
        try:
            active = await self.client.hget(self.control_key, "active")
            if active is None:
                return "not_active"
            if not active.isascii() or not hmac.compare_digest(lease_fingerprint(active), fingerprint):
                return "lease_changed"
            values = await self._recover(keys=[self.control_key], args=[str(self.epoch), identity_key_id, active])
        except RedisError:
            raise AppError("SERVICE_UNAVAILABLE") from None
        result = {"ok": "released", "NOT_ACTIVE": "not_active", "LEASE_CHANGED": "lease_changed"}.get(values[0] if values else None)
        if result is None:
            raise AppError("SERVICE_UNAVAILABLE")
        return result

    async def initialize(self, identity_key_id, *, no_runs_today: bool) -> str:
        """Redis 재시작 등으로 제어 해시가 없을 때 운영자가 새로 만든다.

        기본은 오늘 집계를 한도(500)로 채워 다음 KST 날짜까지 새 추론을 막는다. 집계를 0으로
        되돌려 한도를 우회하지 못하게 하기 위해서다. 운영자가 오늘 실행이 없었음을 확인한
        경우(예: 전날부터 꺼져 있던 서버를 처음 켬)에만 `no_runs_today=True`로 0에서 시작한다.
        이미 해시가 있으면 덮어쓰지 않고 `exists`를 돌려준다.
        """
        if not isinstance(identity_key_id, str) or not re.fullmatch(r"[0-9a-f]{64}", identity_key_id):
            raise ValueError("식별키 지문 형식 오류")
        if no_runs_today is not True and no_runs_today is not False:
            raise ValueError("실행 기록 확인 값은 bool이어야 한다")
        used = 0 if no_runs_today else GLOBAL_DAILY_LIMIT
        try:
            values = await self._initialize(keys=[self.control_key], args=[str(self.epoch), identity_key_id, str(used)])
        except RedisError:
            raise AppError("SERVICE_UNAVAILABLE") from None
        result = {"ok": "initialized", "EXISTS": "exists"}.get(values[0] if isinstance(values, list) and values else None)
        if result is None:
            raise AppError("SERVICE_UNAVAILABLE")
        return result
