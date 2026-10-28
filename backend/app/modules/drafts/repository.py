"""지원서와 생성 저널을 체험 해시 안에 원자 저장한다. 삭제/만료 시 함께 폐기한다."""

from dataclasses import dataclass, field
import secrets
from uuid import UUID, uuid4

from redis.exceptions import RedisError

from app.contracts.drafts import JourneyDraft
from app.core.business_errors import AppError
from app.adapters.journey_lifecycle import _SESSION_LIFETIME, _VIEW
from app.modules.sessions.service import IDLE_MS, ABSOLUTE_MS
from app.modules.requests.service import RESOURCE_MAX_MS

MAX_DRAFTS = 32
MAX_ATTEMPTS = 128


@dataclass(frozen=True)
class DraftPermit:
    key: UUID
    token: str = field(repr=False)
    draft_id: UUID
    revision: int
    profile_version: int
    generation: UUID
    notice_version: str


_BASE = _SESSION_LIFETIME + """
if ARGV[2] ~= '' and (s[4] ~= ARGV[2] or not granted or granted < sc or granted > now) then return {'CONSENT_REQUIRED'} end
""" + _VIEW + """
local state = view(KEYS[2], KEYS[3], false)
if state[1] ~= 'ok' then return state end
"""
_RESERVE = _BASE + """
local field = 'draft-create:' .. ARGV[7] .. ':'
local previous = redis.call('HGET', KEYS[3], field .. 'input')
if previous then
    if previous ~= ARGV[8] then return {'IDEMPOTENCY_KEY_REUSED'} end
    local status = redis.call('HGET', KEYS[3], field .. 'state')
    if status == 'pending' then return {'REQUEST_IN_PROGRESS'} end
    if status == 'cancelled' then return {'REQUEST_ALREADY_COMPLETED'} end
    if status ~= 'done' then return {'SERVICE_UNAVAILABLE'} end
    local result = redis.call('HGET', KEYS[3], field .. 'result')
    if not result then return {'SERVICE_UNAVAILABLE'} end
    return {'replay', result}
end
if state[7] ~= ARGV[9] or redis.call('HGET', KEYS[3], 'confirmed_version') ~= ARGV[10] then return {'VERSION_CONFLICT'} end
local attempts_raw = redis.call('HGET', KEYS[3], 'draft_attempts') or '0'
local count_raw = redis.call('HGET', KEYS[3], 'draft_count') or '0'
local attempts, count = tonumber(attempts_raw), tonumber(count_raw)
if not attempts or not count or not string.match(attempts_raw, '^%d+$') or not string.match(count_raw, '^%d+$') or tostring(attempts) ~= attempts_raw or tostring(count) ~= count_raw then return {'SERVICE_UNAVAILABLE'} end
if attempts >= tonumber(ARGV[13]) or count >= tonumber(ARGV[14]) then return {'RATE_LIMITED'} end
redis.call('HSET', KEYS[3], field .. 'input', ARGV[8], field .. 'state', 'pending', field .. 'token', ARGV[11], field .. 'id', ARGV[12])
redis.call('HINCRBY', KEYS[3], 'draft_attempts', 1)
return {'permit', state[4]}
"""
_COMPLETE = _BASE + """
local field = 'draft-create:' .. ARGV[7] .. ':'
local journal = redis.call('HMGET', KEYS[3], field .. 'state', field .. 'token', field .. 'id')
if journal[1] ~= 'pending' or journal[2] ~= ARGV[8] or journal[3] ~= ARGV[9] then return {'INVALID_STATE_TRANSITION'} end
if state[7] ~= ARGV[10] or state[4] ~= ARGV[12] or redis.call('HGET', KEYS[3], 'confirmed_version') ~= ARGV[11] then return {'VERSION_CONFLICT'} end
local count_raw = redis.call('HGET', KEYS[3], 'draft_count') or '0'
local count = tonumber(count_raw)
if not count or not string.match(count_raw, '^%d+$') or tostring(count) ~= count_raw then return {'SERVICE_UNAVAILABLE'} end
if count >= tonumber(ARGV[14]) then return {'RATE_LIMITED'} end
local draft = 'draft:' .. ARGV[9]
if redis.call('HEXISTS', KEYS[3], draft) == 1 then return {'SERVICE_UNAVAILABLE'} end
redis.call('HSET', KEYS[3], draft, ARGV[13], field .. 'state', 'done', field .. 'result', ARGV[13])
redis.call('HINCRBY', KEYS[3], 'draft_count', 1)
view(KEYS[2], KEYS[3], true)
return {'ok', ARGV[13]}
"""
_CANCEL = _BASE + """
local field = 'draft-create:' .. ARGV[7] .. ':'
if redis.call('HGET', KEYS[3], field .. 'state') == 'pending' and redis.call('HGET', KEYS[3], field .. 'token') == ARGV[8] then
    redis.call('HSET', KEYS[3], field .. 'state', 'cancelled')
end
return {'ok'}
"""
_READ = _BASE + """
local draft = redis.call('HGET', KEYS[3], 'draft:' .. ARGV[7])
if not draft then return {'NOT_FOUND'} end
return {'ok', draft}
"""
_MUTATE = _BASE + """
local field = 'draft:' .. ARGV[7]
local raw = redis.call('HGET', KEYS[3], field)
if not raw then return {'NOT_FOUND'} end
if raw ~= ARGV[8] then return {'VERSION_CONFLICT'} end
if ARGV[10] ~= '' and (state[7] ~= ARGV[10] or redis.call('HGET', KEYS[3], 'confirmed_version') ~= ARGV[11]) then return {'VERSION_CONFLICT'} end
redis.call('HSET', KEYS[3], field, ARGV[9])
view(KEYS[2], KEYS[3], true)
return {'ok', ARGV[9]}
"""


class UnavailableDraftStore:
    async def reserve(self, *args, **kwargs):
        raise AppError('SERVICE_UNAVAILABLE')
    complete = cancel = read = mutate = reserve


class RedisDraftStore:
    def __init__(self, client, *, session_key, resource_key):
        self.session_key, self.resource_key = session_key, resource_key
        self._reserve, self._complete, self._cancel = [client.register_script(script) for script in (_RESERVE, _COMPLETE, _CANCEL)]
        self._read, self._mutate = [client.register_script(script) for script in (_READ, _MUTATE)]

    async def _call(self, script, session, journey_id, notice, extra):
        resource = self.resource_key(session.subject_id, journey_id)
        try:
            values = await script(keys=[self.session_key(session.digest), resource, resource + ':lifecycle'],
                args=[*[str(session.subject_id), notice, IDLE_MS, ABSOLUTE_MS, session.digest, RESOURCE_MAX_MS], *extra])
            if not isinstance(values, list) or not values:
                raise ValueError
            if values[0] in {'NOT_FOUND', 'CONSENT_REQUIRED', 'SERVICE_UNAVAILABLE', 'VERSION_CONFLICT', 'IDEMPOTENCY_KEY_REUSED',
                             'REQUEST_IN_PROGRESS', 'REQUEST_ALREADY_COMPLETED', 'INVALID_STATE_TRANSITION', 'RATE_LIMITED'}:
                raise AppError(values[0], retry_after=1 if values[0] == 'REQUEST_IN_PROGRESS' else None)
            return values
        except (RedisError, ValueError, TypeError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    @staticmethod
    def _draft(raw):
        try:
            if len(raw.encode('utf-8')) > 65536:
                raise ValueError
            return JourneyDraft.model_validate_json(raw)
        except (ValueError, TypeError, AttributeError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def reserve(self, session, journey_id, key, fingerprint, revision, profile_version, notice=''):
        token, draft_id = secrets.token_hex(32), uuid4()
        values = await self._call(self._reserve, session, journey_id, notice,
            [str(key), fingerprint, revision, profile_version, token, str(draft_id), MAX_ATTEMPTS, MAX_DRAFTS])
        if len(values) == 2 and values[0] == 'replay':
            return self._draft(values[1])
        try:
            if len(values) != 2 or values[0] != 'permit':
                raise ValueError
            return DraftPermit(key, token, draft_id, revision, profile_version, UUID(values[1]), notice)
        except (ValueError, TypeError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def complete(self, session, journey_id, permit, draft):
        if (draft.draft_id != permit.draft_id or draft.profile_version != permit.profile_version or draft.revision != 1
            or draft.approved_at is not None or draft.review_reasons or (draft.mode == 'generate') != bool(permit.notice_version)):
            raise AppError('VALIDATION_FAILED')
        values = await self._call(self._complete, session, journey_id, permit.notice_version, [str(permit.key), permit.token,
            str(permit.draft_id), permit.revision, permit.profile_version, str(permit.generation), draft.model_dump_json(), MAX_DRAFTS])
        if len(values) != 2 or values[0] != 'ok':
            raise AppError('SERVICE_UNAVAILABLE')
        return self._draft(values[1])

    async def cancel(self, session, journey_id, permit):
        await self._call(self._cancel, session, journey_id, permit.notice_version, [str(permit.key), permit.token])

    async def read(self, session, journey_id, draft_id):
        values = await self._call(self._read, session, journey_id, '', [str(draft_id)])
        if len(values) != 2 or values[0] != 'ok':
            raise AppError('SERVICE_UNAVAILABLE')
        result = self._draft(values[1])
        if result.draft_id != draft_id:
            raise AppError('SERVICE_UNAVAILABLE')
        return result

    async def mutate(self, session, journey_id, previous, updated, *, journey_revision=None):
        if (updated.draft_id != previous.draft_id or updated.revision != previous.revision + 1
            or updated.mode != previous.mode or updated.profile_version != previous.profile_version or updated.opportunity != previous.opportunity
            or (updated.approved_at is not None and (journey_revision is None or updated.self_introduction != previous.self_introduction or updated.motivation != previous.motivation))):
            raise AppError('VALIDATION_FAILED')
        values = await self._call(self._mutate, session, journey_id, '', [str(previous.draft_id), previous.model_dump_json(),
            updated.model_dump_json(), journey_revision if journey_revision is not None else '', previous.profile_version])
        if len(values) != 2 or values[0] != 'ok':
            raise AppError('SERVICE_UNAVAILABLE')
        return self._draft(values[1])
