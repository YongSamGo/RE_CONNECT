"""단일 Redis: 생성 멱등·주체 한도·체험 상태를 한 스크립트로 확정한다."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import ValidationError
from redis.exceptions import RedisError

from app.contracts.journey import Journey, Message
from app.core.business_errors import AppError
from app.modules.journeys.service import FIRST_QUESTION, JourneyRecord
from app.modules.requests.service import CompletionGuard, RESOURCE_MAX_MS, RETENTION_MS
from app.modules.sessions.service import ABSOLUTE_MS, IDLE_MS

_SESSION = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local s = redis.call('HMGET', KEYS[1], 'subject_id', 'created_ms', 'last_ms', 'ai_notice_version', 'ai_granted_ms')
if not s[1] or s[1] ~= ARGV[1] or redis.call('PTTL', KEYS[1]) <= 0 then return {'NOT_FOUND'} end
local sc, sl, granted = tonumber(s[2]), tonumber(s[3]), tonumber(s[5])
if not sc or not sl or sl < sc or now < sl then return {'SERVICE_UNAVAILABLE'} end
if now >= sc + tonumber(ARGV[4]) or now >= sl + tonumber(ARGV[3]) then return {'NOT_FOUND'} end
if s[4] ~= ARGV[2] or not granted or granted < sc or granted > now then return {'CONSENT_REQUIRED'} end
"""

_VIEW = """
local function view(resource, meta, touch)
    local r = redis.call('HMGET', meta, 'journey_id', 'first_message_id', 'generation', 'created_ms', 'last_ms', 'digest', 'notice_version', 'owner')
    if not r[1] or r[6] ~= ARGV[5] or r[7] ~= ARGV[2] or r[8] ~= ARGV[1] then return {'NOT_FOUND'} end
    local created, last = tonumber(r[4]), tonumber(r[5])
    if not created or not last or last < created or now < last then return {'SERVICE_UNAVAILABLE'} end
    if now >= created + tonumber(ARGV[6]) or now >= last + tonumber(ARGV[3]) then return {'NOT_FOUND'} end
    local revision = redis.call('GET', resource)
    if not revision or not string.match(revision, '^g:%d+$') or redis.call('PTTL', meta) <= 0 or redis.call('PTTL', resource) <= 0 then return {'NOT_FOUND'} end
    if touch then
        r[5] = tostring(now)
        redis.call('HSET', meta, 'last_ms', now)
        local ttl = math.min(tonumber(ARGV[3]), created + tonumber(ARGV[6]) - now)
        redis.call('PEXPIRE', meta, ttl)
        redis.call('PEXPIRE', resource, ttl)
    end
    return {'ok', r[1], r[2], r[3], r[4], r[5], string.sub(revision, 3)}
end
"""

_CREATE = _SESSION + _VIEW + """
local journal = redis.call('HMGET', KEYS[2], 'input', 'resource', 'meta')
if journal[1] then
    if journal[1] ~= ARGV[7] then return {'IDEMPOTENCY_KEY_REUSED'} end
    if not journal[2] or not journal[3] or redis.call('PTTL', KEYS[2]) <= 0 then return {'SERVICE_UNAVAILABLE'} end
    return view(journal[2], journal[3], false)
end
if redis.call('EXISTS', KEYS[2]) == 1 then return {'SERVICE_UNAVAILABLE'} end
local control = redis.call('HMGET', KEYS[5], 'epoch', 'key_id', 'day', 'global')
if control[1] ~= ARGV[11] or control[2] ~= ARGV[12] or redis.call('PTTL', KEYS[5]) ~= -1 then return {'SERVICE_UNAVAILABLE'} end
if not control[3] or not string.match(control[3], '^%d+$') or not control[4] or not string.match(control[4], '^%d+$') then return {'SERVICE_UNAVAILABLE'} end
local day = math.floor((tonumber(t[1]) + 32400) / 86400)
local retry = (day + 1) * 86400 - 32400 - tonumber(t[1])
if tonumber(control[3]) > day then return {'SERVICE_UNAVAILABLE'} end
if tonumber(control[3]) < day then
    for _, key in ipairs(redis.call('HKEYS', KEYS[5])) do
        if string.sub(key, 1, 6) == 'limit:' then redis.call('HDEL', KEYS[5], key) end
    end
    redis.call('HSET', KEYS[5], 'day', day, 'global', 0)
end
local count = redis.call('HGET', KEYS[5], 'limit:' .. ARGV[13])
if count and not string.match(count, '^%d+$') then return {'SERVICE_UNAVAILABLE'} end
if count and tonumber(count) >= 60 then return {'DAILY_QUOTA_EXCEEDED', tostring(retry)} end
if redis.call('EXISTS', KEYS[3]) == 1 or redis.call('EXISTS', KEYS[4]) == 1 then return {'SERVICE_UNAVAILABLE'} end
redis.call('SET', KEYS[3], 'g:1', 'PX', ARGV[3])
redis.call('HSET', KEYS[4], 'journey_id', ARGV[8], 'first_message_id', ARGV[9], 'generation', ARGV[10],
    'created_ms', now, 'last_ms', now, 'digest', ARGV[5], 'notice_version', ARGV[2], 'owner', ARGV[1])
redis.call('PEXPIRE', KEYS[4], ARGV[3])
redis.call('HSET', KEYS[2], 'input', ARGV[7], 'resource', KEYS[3], 'meta', KEYS[4])
redis.call('PEXPIRE', KEYS[2], ARGV[14])
redis.call('HINCRBY', KEYS[5], 'limit:' .. ARGV[13], 1)
return view(KEYS[3], KEYS[4], false)
"""

_LOAD = _SESSION + _VIEW + "return view(KEYS[2], KEYS[3], ARGV[7] == '1')"


class RedisJourneyStore:
    def __init__(self, client, *, session_key, resource_key, control_key: str, epoch: UUID,
                 prefix: str = "rc:journey:v1:"):
        self._create = client.register_script(_CREATE)
        self._load = client.register_script(_LOAD)
        self.session_key, self.resource_key = session_key, resource_key
        self.control_key, self.epoch, self.prefix = control_key, epoch, prefix

    @staticmethod
    def _args(session, version):
        return [str(session.subject_id), version, IDLE_MS, ABSOLUTE_MS, session.digest, RESOURCE_MAX_MS]

    async def _call(self, script, keys, args, session, version):
        try:
            values = await script(keys=keys, args=args)
            if not isinstance(values, list) or not values:
                raise ValueError
            if values[0] in {"NOT_FOUND", "CONSENT_REQUIRED", "IDEMPOTENCY_KEY_REUSED", "SERVICE_UNAVAILABLE"}:
                raise AppError(values[0])
            if values[0] == "DAILY_QUOTA_EXCEEDED":
                raise AppError(values[0], retry_after=int(values[1]))
            status, journey, message, generation, created, last, revision = values
            if status != "ok":
                raise ValueError
            created, last = int(created), int(last)
            if not 0 <= created <= last:
                raise ValueError
            def timestamp(value):
                return datetime.fromtimestamp(value / 1000, UTC)
            view = Journey(journey_id=UUID(journey), revision=int(revision), expires_at=timestamp(created + RESOURCE_MAX_MS),
                           idle_expires_at=timestamp(min(last + IDLE_MS, created + RESOURCE_MAX_MS)),
                           first_message=Message(message_id=UUID(message), text=FIRST_QUESTION, created_at=timestamp(created)), confirmed=None)
            return JourneyRecord(view, CompletionGuard(session.digest, UUID(generation), version))
        except (RedisError, ValueError, TypeError, IndexError, OverflowError, OSError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    async def create(self, session, key_id, fingerprint, notice_version, budget, key_id_digest):
        journey, message, generation = uuid4(), uuid4(), uuid4()
        resource = self.resource_key(session.subject_id, journey)
        journal = self.prefix + hashlib.sha256(f"{session.subject_id}:{key_id}".encode("ascii")).hexdigest()
        return await self._call(self._create,
            [self.session_key(session.digest), journal, resource, resource + ":lifecycle", self.control_key],
            [*self._args(session, notice_version), fingerprint, str(journey), str(message), str(generation),
             str(self.epoch), key_id_digest, budget, RETENTION_MS], session, notice_version)

    async def load(self, session, journey_id, notice_version, *, user_activity=False):
        resource = self.resource_key(session.subject_id, journey_id)
        return await self._call(self._load, [self.session_key(session.digest), resource, resource + ":lifecycle"],
                                [*self._args(session, notice_version), "1" if user_activity else "0"], session, notice_version)
