"""원본 오디오 없이 전사 JSON/생성 저널만 체험 lifecycle 해시에 둔다."""

from dataclasses import dataclass, field
import secrets
from uuid import UUID, uuid4

from redis.exceptions import RedisError

from app.adapters.journey_lifecycle import _SESSION_LIFETIME, _VIEW
from app.contracts.journey import Transcription
from app.core.business_errors import AppError
from app.modules.sessions.service import IDLE_MS, ABSOLUTE_MS
from app.modules.requests.service import RESOURCE_MAX_MS


@dataclass(frozen=True)
class TranscriptionPermit:
    key: UUID
    token: str = field(repr=False)
    transcription_id: UUID
    revision: int
    generation: UUID
    notice: str


_BASE = _SESSION_LIFETIME + """
if s[4] ~= ARGV[2] or not granted or granted < sc or granted > now then return {'CONSENT_REQUIRED'} end
""" + _VIEW + """
local state = view(KEYS[2], KEYS[3], false)
if state[1] ~= 'ok' then return state end
"""
_BEGIN = _BASE + """
local field = 'transcription-create:' .. ARGV[7] .. ':'
local prior = redis.call('HGET', KEYS[3], field .. 'input')
if prior then
    if prior ~= ARGV[8] then return {'IDEMPOTENCY_KEY_REUSED'} end
    local status = redis.call('HGET', KEYS[3], field .. 'state')
    if status == 'pending' then return {'REQUEST_IN_PROGRESS'} end
    if status == 'cancelled' then return {'REQUEST_ALREADY_COMPLETED'} end
    local result = redis.call('HGET', KEYS[3], field .. 'result')
    if status ~= 'done' or not result then return {'SERVICE_UNAVAILABLE'} end
    return {'replay', result}
end
if state[7] ~= ARGV[9] then return {'VERSION_CONFLICT'} end
local attempts_raw = redis.call('HGET', KEYS[3], 'transcription_attempts') or '0'
local count_raw = redis.call('HGET', KEYS[3], 'transcription_count') or '0'
local attempts, count = tonumber(attempts_raw), tonumber(count_raw)
if not attempts or not count or not string.match(attempts_raw, '^%d+$') or not string.match(count_raw, '^%d+$') or tostring(attempts) ~= attempts_raw or tostring(count) ~= count_raw then return {'SERVICE_UNAVAILABLE'} end
if attempts >= 128 or count >= 64 then return {'RATE_LIMITED'} end
redis.call('HSET', KEYS[3], field .. 'input', ARGV[8], field .. 'state', 'pending', field .. 'token', ARGV[10], field .. 'id', ARGV[11])
redis.call('HINCRBY', KEYS[3], 'transcription_attempts', 1)
return {'permit', state[4]}
"""
_COMPLETE = _BASE + """
local field = 'transcription-create:' .. ARGV[7] .. ':'
local j = redis.call('HMGET', KEYS[3], field .. 'state', field .. 'token', field .. 'id')
if j[1] ~= 'pending' or j[2] ~= ARGV[8] or j[3] ~= ARGV[9] then return {'INVALID_STATE_TRANSITION'} end
if state[7] ~= ARGV[10] or state[4] ~= ARGV[11] then return {'VERSION_CONFLICT'} end
local count_raw = redis.call('HGET', KEYS[3], 'transcription_count') or '0'
local count = tonumber(count_raw)
if not count or not string.match(count_raw, '^%d+$') or tostring(count) ~= count_raw then return {'SERVICE_UNAVAILABLE'} end
if count >= 64 then return {'RATE_LIMITED'} end
if redis.call('HEXISTS', KEYS[3], 'transcription:' .. ARGV[9]) == 1 then return {'SERVICE_UNAVAILABLE'} end
redis.call('HSET', KEYS[3], 'transcription:' .. ARGV[9], ARGV[12], field .. 'state', 'done', field .. 'result', ARGV[12])
redis.call('HINCRBY', KEYS[3], 'transcription_count', 1)
view(KEYS[2], KEYS[3], true)
return {'ok', ARGV[12]}
"""
_READ = _BASE + """
local result = redis.call('HGET', KEYS[3], 'transcription:' .. ARGV[7])
if not result then return {'NOT_FOUND'} end
return {'ok', result}
"""
_CANCEL = _BASE + """
local field = 'transcription-create:' .. ARGV[7] .. ':'
if redis.call('HGET', KEYS[3], field .. 'state') == 'pending' and redis.call('HGET', KEYS[3], field .. 'token') == ARGV[8] then
    redis.call('HSET', KEYS[3], field .. 'state', 'cancelled')
end
return {'ok'}
"""


class UnavailableTranscriptionStore:
    async def begin(self, *args, **kwargs):
        raise AppError('SERVICE_UNAVAILABLE')
    complete = read = cancel = begin


class RedisTranscriptionStore:
    def __init__(self, client, *, session_key, resource_key):
        self.session_key, self.resource_key = session_key, resource_key
        self._begin, self._complete, self._read, self._cancel = [client.register_script(script) for script in (_BEGIN, _COMPLETE, _READ, _CANCEL)]

    async def _call(self, script, session, journey, notice, extra):
        resource = self.resource_key(session.subject_id, journey)
        try:
            values = await script(keys=[self.session_key(session.digest), resource, resource + ':lifecycle'],
                args=[str(session.subject_id), notice, IDLE_MS, ABSOLUTE_MS, session.digest, RESOURCE_MAX_MS, *extra])
            if not isinstance(values, list) or not values:
                raise ValueError
            if values[0] in {'NOT_FOUND', 'CONSENT_REQUIRED', 'VERSION_CONFLICT', 'SERVICE_UNAVAILABLE', 'IDEMPOTENCY_KEY_REUSED',
                'REQUEST_IN_PROGRESS', 'REQUEST_ALREADY_COMPLETED', 'INVALID_STATE_TRANSITION', 'RATE_LIMITED'}:
                raise AppError(values[0], retry_after=1 if values[0] == 'REQUEST_IN_PROGRESS' else None)
            return values
        except (RedisError, ValueError, TypeError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    @staticmethod
    def _result(values):
        try:
            if len(values) != 2 or values[0] not in {'ok', 'replay'} or len(values[1].encode('utf-8')) > 16384:
                raise ValueError
            return Transcription.model_validate_json(values[1])
        except (ValueError, TypeError, AttributeError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def begin(self, session, journey, key, fingerprint, revision, notice):
        token, transcription = secrets.token_hex(32), uuid4()
        values = await self._call(self._begin, session, journey, notice, [str(key), fingerprint, revision, token, str(transcription)])
        if values[0] == 'replay':
            return self._result(values)
        try:
            if len(values) != 2 or values[0] != 'permit':
                raise ValueError
            return TranscriptionPermit(key, token, transcription, revision, UUID(values[1]), notice)
        except (ValueError, TypeError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def complete(self, session, journey, permit, result):
        if result.transcription_id != permit.transcription_id:
            raise AppError('VALIDATION_FAILED')
        return self._result(await self._call(self._complete, session, journey, permit.notice, [str(permit.key), permit.token,
            str(result.transcription_id), permit.revision, str(permit.generation), result.model_dump_json()]))

    async def read(self, session, journey, transcription, notice):
        result = self._result(await self._call(self._read, session, journey, notice, [str(transcription)]))
        if result.transcription_id != transcription:
            raise AppError('SERVICE_UNAVAILABLE')
        return result

    async def cancel(self, session, journey, permit):
        await self._call(self._cancel, session, journey, permit.notice, [str(permit.key), permit.token])
