"""단일 Redis용 원자 예약·완료·CAS. 임계 구간에서 외부 추론을 실행하지 않는다."""

import hashlib
import json
import re
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.business_errors import AppError
from app.modules.requests.service import Permit, Replay, RequestScope, ResultReference, RETENTION_MS

MAX_RESOURCE_REQUESTS = 256

_BEGIN = """
local ttl = tonumber(ARGV[4])
if ARGV[5] ~= '' then
    local revision = redis.call('GET', KEYS[2])
    ttl = redis.call('PTTL', KEYS[2])
    if not revision or ttl <= 0 then return {'NOT_FOUND'} end
    if not tonumber(revision) then return redis.error_reply('Invalid revision') end
end
if redis.call('EXISTS', KEYS[1]) == 1 then
    local v = redis.call('HMGET', KEYS[1], 'input', 'state', 'result')
    if not v[1] or not v[2] or not v[3] or redis.call('PTTL', KEYS[1]) <= 0 then
        return redis.error_reply('Invalid request state')
    end
    if v[1] ~= ARGV[1] then return {'IDEMPOTENCY_KEY_REUSED'} end
    if v[2] == 'pending' then return {'REQUEST_IN_PROGRESS'} end
    if v[2] == 'conflict' then return {'VERSION_CONFLICT'} end
    if v[2] ~= 'done' then return redis.error_reply('Invalid request state') end
    if v[3] == '' then return {'REQUEST_ALREADY_COMPLETED'} end
    return {'replay', v[3]}
end
if ARGV[5] ~= '' then
    if redis.call('GET', KEYS[2]) ~= ARGV[5] then return {'VERSION_CONFLICT'} end
    if redis.call('SCARD', KEYS[3]) >= tonumber(ARGV[6]) then return {'RATE_LIMITED'} end
    redis.call('SADD', KEYS[3], KEYS[1])
    redis.call('PEXPIRE', KEYS[3], ttl)
end
redis.call('HSET', KEYS[1], 'input', ARGV[1], 'execution', ARGV[2], 'state', 'pending', 'result', '')
redis.call('PEXPIRE', KEYS[1], math.min(ttl, tonumber(ARGV[4])))
return {'permit'}
"""

_COMPLETE = """
if ARGV[4] ~= '' and (redis.call('EXISTS', KEYS[2]) == 0 or redis.call('PTTL', KEYS[2]) <= 0) then
    return {'NOT_FOUND'}
end
local v = redis.call('HMGET', KEYS[1], 'input', 'execution', 'state', 'result')
if not v[1] or redis.call('PTTL', KEYS[1]) <= 0 then return {'NOT_FOUND'} end
if v[1] ~= ARGV[1] or v[2] ~= ARGV[2] then return {'IDEMPOTENCY_KEY_REUSED'} end
if v[3] == 'conflict' then return {'VERSION_CONFLICT'} end
if v[3] == 'done' then
    if v[4] ~= ARGV[3] then return {'IDEMPOTENCY_KEY_REUSED'} end
    return {'ok'}
end
if v[3] ~= 'pending' then return redis.error_reply('Invalid request state') end
if ARGV[4] ~= '' then
    if redis.call('GET', KEYS[2]) ~= ARGV[4] then
        redis.call('HSET', KEYS[1], 'state', 'conflict')
        return {'VERSION_CONFLICT'}
    end
    -- 증분과 완료 기록은 같은 스크립트에서 확정한다. 응답 유실 재시도는 다시 증분하지 않는다.
    redis.call('INCR', KEYS[2])
end
redis.call('HSET', KEYS[1], 'state', 'done', 'result', ARGV[3])
return {'ok'}
"""

_DELETE = """
local keys = redis.call('SMEMBERS', KEYS[2])
for _, key in ipairs(keys) do redis.call('DEL', key) end
redis.call('DEL', KEYS[1], KEYS[2])
return 1
"""


class RedisRequestStore:
    def __init__(self, client: Redis, *, prefix: str = "rc:request:v1:"):
        self.client = client
        self.prefix = prefix
        self._begin = client.register_script(_BEGIN)
        self._complete = client.register_script(_COMPLETE)
        self._delete = client.register_script(_DELETE)

    def resource_key(self, subject_id: UUID, resource_id: UUID) -> str:
        digest = hashlib.sha256(f"{subject_id}:{resource_id}".encode("ascii")).hexdigest()
        return self.prefix + "resource:" + digest

    def keys(self, scope: RequestScope, key_id: UUID) -> list[str]:
        identity = json.dumps([str(scope.subject_id), str(scope.resource_id), scope.api, str(key_id)], separators=(",", ":"))
        request = self.prefix + hashlib.sha256(identity.encode("ascii")).hexdigest()
        resource = self.resource_key(scope.subject_id, scope.resource_id) if scope.resource_id else self.prefix + "unused"
        return [request, resource, resource + ":requests"]

    async def _call(self, script, *, keys, args):
        try:
            return await script(keys=keys, args=args)
        except RedisError:
            raise AppError("SERVICE_UNAVAILABLE") from None

    @staticmethod
    def _check_permit(permit: Permit):
        if not re.fullmatch(r"[0-9a-f]{64}", permit.input_hash) or not re.fullmatch(r"[0-9a-f]{64}", permit.execution_id):
            raise ValueError("실행 권한 형식 오류")

    @staticmethod
    def _outcome(values):
        if not isinstance(values, list) or not values:
            raise AppError("SERVICE_UNAVAILABLE")
        code = values[0]
        if code in {"NOT_FOUND", "IDEMPOTENCY_KEY_REUSED", "VERSION_CONFLICT", "REQUEST_ALREADY_COMPLETED"}:
            raise AppError(code)
        if code == "REQUEST_IN_PROGRESS":
            raise AppError(code, retry_after=2)
        if code == "RATE_LIMITED":
            raise AppError(code, retry_after=60)
        return code

    async def begin(self, permit: Permit) -> Permit | Replay:
        self._check_permit(permit)
        values = await self._call(self._begin, keys=self.keys(permit.scope, permit.key_id), args=[permit.input_hash, permit.execution_id, "", RETENTION_MS, "" if permit.base_revision is None else str(permit.base_revision), MAX_RESOURCE_REQUESTS])
        code = self._outcome(values)
        if code == "permit" and len(values) == 1:
            return permit
        if code == "replay" and len(values) == 2:
            try:
                raw = json.loads(values[1])
                if type(raw) is not list or len(raw) != 3:
                    raise ValueError
                return Replay(ResultReference(raw[0], UUID(raw[1]), raw[2]))
            except (TypeError, ValueError, AttributeError):
                raise AppError("SERVICE_UNAVAILABLE") from None
        raise AppError("SERVICE_UNAVAILABLE")

    async def complete(self, permit: Permit, result: ResultReference | None) -> None:
        self._check_permit(permit)
        encoded = "" if result is None else json.dumps([result.kind, str(result.id), result.version], separators=(",", ":"))
        values = await self._call(self._complete, keys=self.keys(permit.scope, permit.key_id)[:2], args=[permit.input_hash, permit.execution_id, encoded, "" if permit.base_revision is None else str(permit.base_revision)])
        if self._outcome(values) != "ok" or len(values) != 1:
            raise AppError("SERVICE_UNAVAILABLE")

    async def create_resource(self, subject_id: UUID, resource_id: UUID, ttl_ms: int) -> bool:
        try:
            return bool(await self.client.set(self.resource_key(subject_id, resource_id), "0", nx=True, px=ttl_ms))
        except RedisError:
            raise AppError("SERVICE_UNAVAILABLE") from None

    async def delete_resource(self, subject_id: UUID, resource_id: UUID) -> None:
        key = self.resource_key(subject_id, resource_id)
        await self._call(self._delete, keys=[key, key + ":requests"], args=[])
