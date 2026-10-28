"""신고 접수의 멱등 기록과 하루 한도를 한 스크립트로 확정한다 (단일 Redis).

신고자는 DB에 남기지 않는다. 한도와 멱등 기록은 HMAC 식별값만 쓰고 24시간 안에 사라진다.
같은 주체가 같은 공고에 하루 1건, 주체당 하루 10건, IP당 하루 30건이다(KST 날짜 기준).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import re
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.business_errors import AppError

PER_OPPORTUNITY = 1
PER_SUBJECT = 10
PER_IP = 30
RECEIPT_TTL_MS = 24 * 60 * 60 * 1000

# KEYS[1] 멱등 기록, KEYS[2] 오늘 집계.
# ARGV: 입력 해시, 새 신고 ID, 조회만(1/0), 주체·IP·주체+공고 식별값, 세 한도, 멱등 기록 수명.
_RESERVE = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local v = redis.call('HMGET', KEYS[1], 'input', 'report', 'at')
if v[1] then
    if not v[2] or not v[3] then return {'SERVICE_UNAVAILABLE'} end
    if v[1] ~= ARGV[1] then return {'IDEMPOTENCY_KEY_REUSED'} end
    return {'replay', v[2], v[3]}
end
if ARGV[3] == '1' then return {'none'} end
local day = math.floor((tonumber(t[1]) + 32400) / 86400)
local retry = (day + 1) * 86400 - 32400 - tonumber(t[1])
local current = redis.call('HGET', KEYS[2], 'day')
if current and not string.match(current, '^%d+$') then return {'SERVICE_UNAVAILABLE'} end
if current and tonumber(current) > day then return {'SERVICE_UNAVAILABLE'} end
if not current or tonumber(current) < day then
    redis.call('DEL', KEYS[2])
    redis.call('HSET', KEYS[2], 'day', day)
end
local fields = {'o:' .. ARGV[6], 's:' .. ARGV[4], 'i:' .. ARGV[5]}
local limits = {tonumber(ARGV[7]), tonumber(ARGV[8]), tonumber(ARGV[9])}
for index, field in ipairs(fields) do
    local count = redis.call('HGET', KEYS[2], field)
    if count and not string.match(count, '^%d+$') then return {'SERVICE_UNAVAILABLE'} end
    if count and tonumber(count) >= limits[index] then return {'DAILY_QUOTA_EXCEEDED', tostring(retry)} end
end
for _, field in ipairs(fields) do redis.call('HINCRBY', KEYS[2], field, 1) end
redis.call('PEXPIRE', KEYS[2], 2 * 86400000)
redis.call('HSET', KEYS[1], 'input', ARGV[1], 'report', ARGV[2], 'at', now)
redis.call('PEXPIRE', KEYS[1], ARGV[10])
return {'new', ARGV[2], tostring(now)}
"""

_DIGEST = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class Reservation:
    report_id: UUID
    received_at: datetime
    replay: bool


@dataclass(frozen=True)
class ReportIdentity:
    """서버가 정한 HMAC 식별값. 원래 IP·주체 ID는 담지 않는다."""

    subject: str
    ip: str
    subject_opportunity: str

    def __post_init__(self):
        values = (self.subject, self.ip, self.subject_opportunity)
        if any(not isinstance(value, str) or not _DIGEST.fullmatch(value) for value in values) or len(set(values)) != 3:
            raise ValueError("신고 한도 식별값 형식 오류")


class RedisReportStore:
    def __init__(self, client: Redis, *, prefix: str = "rc:report:v1:"):
        self.client = client
        self.prefix = prefix
        self.limits_key = prefix + "limits"
        self._reserve = client.register_script(_RESERVE)

    def receipt_key(self, subject: str, key_id: UUID) -> str:
        identity = json.dumps([subject, str(key_id)], separators=(",", ":"))
        return self.prefix + "receipt:" + hashlib.sha256(identity.encode("ascii")).hexdigest()

    async def reserve(self, identity: ReportIdentity, key_id: UUID, input_hash: str, report_id: UUID, *, peek: bool) -> Reservation | None:
        if not isinstance(identity, ReportIdentity) or not isinstance(key_id, UUID) or not isinstance(report_id, UUID) or not _DIGEST.fullmatch(input_hash):
            raise ValueError("신고 접수 기록 형식 오류")
        try:
            values = await self._reserve(keys=[self.receipt_key(identity.subject, key_id), self.limits_key], args=[
                input_hash, str(report_id), "1" if peek else "0", identity.subject, identity.ip, identity.subject_opportunity,
                PER_OPPORTUNITY, PER_SUBJECT, PER_IP, RECEIPT_TTL_MS])
        except RedisError:
            raise AppError("SERVICE_UNAVAILABLE") from None
        if values == ["none"] and peek:
            return None
        if isinstance(values, list) and values[:1] == ["IDEMPOTENCY_KEY_REUSED"] and len(values) == 1:
            raise AppError("IDEMPOTENCY_KEY_REUSED")
        if isinstance(values, list) and values[:1] == ["DAILY_QUOTA_EXCEEDED"] and len(values) == 2:
            try:
                retry = int(values[1])
                if not 1 <= retry <= 86400:
                    raise ValueError
            except (TypeError, ValueError):
                raise AppError("SERVICE_UNAVAILABLE") from None
            raise AppError("DAILY_QUOTA_EXCEEDED", retry_after=retry)
        if isinstance(values, list) and len(values) == 3 and values[0] in ("new", "replay"):
            try:
                at_ms = int(values[2])
                if not 0 < at_ms < 2**53:
                    raise ValueError
                return Reservation(UUID(values[1]), datetime.fromtimestamp(at_ms / 1000, UTC), values[0] == "replay")
            except (TypeError, ValueError, OverflowError):
                raise AppError("SERVICE_UNAVAILABLE") from None
        raise AppError("SERVICE_UNAVAILABLE")


class UnavailableReportStore:
    async def reserve(self, *args, **kwargs):
        raise AppError("SERVICE_UNAVAILABLE")
