"""승인본 조회·대기 복사를 한 Lua로 확정한다. 브라우저 본문은 받지 않는다."""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import ValidationError
from redis.exceptions import RedisError

from app.adapters.journey_lifecycle import _SESSION_LIFETIME, _VIEW
from app.contracts.save_intents import SaveIntent
from app.core.business_errors import AppError
from app.modules.sessions.service import ABSOLUTE_MS, IDLE_MS
from app.modules.requests.service import RESOURCE_MAX_MS

INTENT_MS = 600000

_CREATE = _SESSION_LIFETIME + _VIEW + """
if redis.call('HGET', KEYS[1], 'user_id') then return {'ALREADY_SIGNED_IN'} end
local journal = 'intent-key:' .. ARGV[7]
local previous = redis.call('HGET', KEYS[1], journal)
if previous then
    local prior = cjson.decode(previous)
    if prior.input ~= ARGV[8] then return {'IDEMPOTENCY_KEY_REUSED'} end
    if redis.call('HGET', KEYS[4], 'id') ~= prior.id then return {'REQUEST_ALREADY_COMPLETED'} end
    local expires = tonumber(redis.call('HGET', KEYS[4], 'expires_ms'))
    if not expires or expires <= now or redis.call('PTTL', KEYS[4]) <= 0 then return {'REQUEST_ALREADY_COMPLETED'} end
    return {'ok', prior.id, tostring(expires), redis.call('HGET', KEYS[4], 'has_draft')}
end
local count = tonumber(redis.call('HGET', KEYS[1], 'intent_count') or '0')
if not count or count < 0 then return {'SERVICE_UNAVAILABLE'} end
if count >= 32 then return {'RATE_LIMITED', tostring(math.max(1, math.ceil(math.min(sc + tonumber(ARGV[4]) - now, sl + tonumber(ARGV[3]) - now) / 1000)))} end
local state = view(KEYS[2], KEYS[3], false)
if state[1] ~= 'ok' then return state end
local version = redis.call('HGET', KEYS[3], 'confirmed_version')
if not version then return {'PROFILE_NOT_CONFIRMED'} end
if version ~= ARGV[9] then return {'VERSION_CONFLICT'} end
local profile = redis.call('HGET', KEYS[3], 'confirmed:' .. version .. ':content')
local confirmed = redis.call('HGET', KEYS[3], 'confirmed:' .. version .. ':at')
if not profile or not confirmed then return {'SERVICE_UNAVAILABLE'} end
local draft = ''
if ARGV[10] ~= '' then
    draft = redis.call('HGET', KEYS[3], 'draft:' .. ARGV[10])
    if not draft then return {'NOT_FOUND'} end
    local d = cjson.decode(draft)
    if d.revision ~= tonumber(ARGV[11]) or d.profile_version ~= tonumber(version) then return {'VERSION_CONFLICT'} end
    if not d.approved_at or d.approved_at == cjson.null then return {'DRAFT_NOT_APPROVED'} end
    if #d.review_reasons > 0 then return {'DRAFT_NOT_APPROVED'} end
end
local payload = cjson.encode({profile=profile,confirmed_ms=confirmed,draft=draft})
if #payload > 98304 then return {'PAYLOAD_TOO_LARGE'} end
local expires = now + math.min(600000, sc + tonumber(ARGV[4]) - now, sl + tonumber(ARGV[3]) - now)
redis.call('DEL', KEYS[4])
redis.call('HSET', KEYS[4], 'id', ARGV[12], 'expires_ms', expires, 'payload', payload,
    'subject_id', ARGV[1], 'user_id', '', 'has_draft', ARGV[10] == '' and '0' or '1')
redis.call('PEXPIREAT', KEYS[4], expires)
redis.call('HSET', KEYS[1], journal, cjson.encode({input=ARGV[8],id=ARGV[12]}))
redis.call('HINCRBY', KEYS[1], 'intent_count', 1)
return {'ok', ARGV[12], tostring(expires), ARGV[10] == '' and '0' or '1'}
"""

_PENDING = _SESSION_LIFETIME + """
local values = redis.call('HMGET', KEYS[2], 'id', 'expires_ms', 'subject_id', 'user_id', 'has_draft')
if not values[1] then return {} end
local expires = tonumber(values[2])
if not expires or expires <= now or redis.call('PTTL', KEYS[2]) <= 0 then return {} end
if values[3] ~= ARGV[1] or values[4] ~= ARGV[7] then return {} end
if (redis.call('HGET', KEYS[1], 'user_id') or '') ~= ARGV[7] then return {} end
if ARGV[8] ~= '' and ARGV[8] ~= values[1] then return {} end
if ARGV[9] == 'discard' then redis.call('DEL', KEYS[2]); return {} end
if ARGV[9] == 'take' or ARGV[9] == 'peek' then
    local payload = redis.call('HGET', KEYS[2], 'payload')
    if not payload then return {'SERVICE_UNAVAILABLE'} end
    if ARGV[9] == 'take' then redis.call('DEL', KEYS[2]) end
    return {'payload', payload}
end
return {'ok', values[1], values[2], values[5]}
"""


class UnavailableSaveIntentStore:
    async def create(self, *args, **kwargs):
        raise AppError('SERVICE_UNAVAILABLE')

    pending = take = discard = create


class RedisSaveIntentStore:
    def __init__(self, client, *, session_key, resource_key):
        self.session_key, self.resource_key = session_key, resource_key
        self._create, self._pending = [client.register_script(s) for s in (_CREATE, _PENDING)]

    def key(self, digest):
        return self.session_key(digest) + ':save-intent'

    @staticmethod
    def args(session):
        return [str(session.subject_id), '', IDLE_MS, ABSOLUTE_MS, session.digest, RESOURCE_MAX_MS]

    @staticmethod
    def view(values):
        if not values:
            return None
        status, identity, expires, draft = values
        if status != 'ok' or draft not in {'0', '1'}:
            raise ValueError
        return SaveIntent(save_intent_id=UUID(identity), expires_at=datetime.fromtimestamp(int(expires) / 1000, UTC),
                          targets={'profile': True, 'draft': draft == '1'})

    async def _run(self, script, keys, args):
        try:
            values = await script(keys=keys, args=args)
            if values and values[0] == 'RATE_LIMITED':
                raise AppError('RATE_LIMITED', retry_after=int(values[1]))
            if values and values[0] not in {'ok', 'payload'}:
                code = values[0]
                if code not in {'ALREADY_SIGNED_IN', 'IDEMPOTENCY_KEY_REUSED', 'REQUEST_ALREADY_COMPLETED', 'RATE_LIMITED',
                                'SERVICE_UNAVAILABLE', 'NOT_FOUND', 'VERSION_CONFLICT', 'PROFILE_NOT_CONFIRMED',
                                'DRAFT_NOT_APPROVED', 'PAYLOAD_TOO_LARGE'}:
                    code = 'SERVICE_UNAVAILABLE'
                raise AppError(code)
            return values
        except (RedisError, ValueError, TypeError, IndexError, OverflowError, ValidationError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def create(self, session, key, fingerprint, body):
        resource = self.resource_key(session.subject_id, body.journey_id)
        values = await self._run(self._create, [self.session_key(session.digest), resource, resource + ':lifecycle', self.key(session.digest)],
            [*self.args(session), str(key), fingerprint, body.profile.version, str(body.draft.draft_id) if body.draft else '',
             body.draft.revision if body.draft else '', str(uuid4())])
        try:
            return self.view(values)
        except (ValueError, TypeError, OverflowError, ValidationError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def pending(self, session, user_id=None, *, expected=None):
        values = await self._run(self._pending, [self.session_key(session.digest), self.key(session.digest)],
            [*self.args(session), str(user_id) if user_id else '', str(expected) if expected else '', 'read'])
        try:
            return self.view(values)
        except (ValueError, TypeError, OverflowError, ValidationError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def take(self, session, user_id, identity, *, consume=True):
        values = await self._run(self._pending, [self.session_key(session.digest), self.key(session.digest)],
            [*self.args(session), str(user_id), str(identity), 'take' if consume else 'peek'])
        if not values:
            raise AppError('SAVE_INTENT_NOT_FOUND')
        if len(values) != 2 or values[0] != 'payload':
            raise AppError('SERVICE_UNAVAILABLE')
        try:
            return json.loads(values[1])
        except (ValueError, TypeError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def discard(self, session, identity):
        await self._run(self._pending, [self.session_key(session.digest), self.key(session.digest)],
            [*self.args(session), str(session.user_id) if session.user_id else '', str(identity), 'discard'])
