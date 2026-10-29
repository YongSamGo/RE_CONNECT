"""단일 Redis: 생성 멱등·주체 한도·체험 상태를 한 스크립트로 확정한다."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import ValidationError
from redis.exceptions import RedisError
from app.adapters.journey_lifecycle import _SESSION_LIFETIME, _VIEW

from app.contracts.journey import Journey, Message, ConfirmedVersion, ProfileDraftView, ProfileConfirmResult, ProfileRef
from app.contracts.profile import ProfileContent, empty_profile_content
from app.contracts.roles import RoleExclusionUpdate, RoleExclusions
from app.core.business_errors import AppError
from app.modules.journeys.service import FIRST_QUESTION, JourneyRecord, MissingProfileFields, ResolvedJourneyProfile, RoleState
from app.modules.requests.service import CompletionGuard, MAX_RESOURCE_REQUESTS, RESOURCE_MAX_MS, RETENTION_MS
from app.modules.sessions.service import ABSOLUTE_MS, IDLE_MS

MAX_CONFIRMED_VERSIONS = 64

_SESSION = _SESSION_LIFETIME + "if s[4] ~= ARGV[2] or not granted or granted < sc or granted > now then return {'CONSENT_REQUIRED'} end\n"

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
local imported_at = ARGV[16] == '1' and tonumber(ARGV[17]) or nil
if ARGV[16] == '1' and (not imported_at or imported_at <= 0 or imported_at > now) then return {'SERVICE_UNAVAILABLE'} end
if redis.call('SCARD', KEYS[6]) >= 60 then return {'DAILY_QUOTA_EXCEEDED', tostring(retry)} end
redis.call('SADD', KEYS[6], KEYS[3])
redis.call('PEXPIREAT', KEYS[6], sc + tonumber(ARGV[4]))
redis.call('SET', KEYS[3], 'g:1', 'PX', ARGV[3])
redis.call('HSET', KEYS[4], 'journey_id', ARGV[8], 'first_message_id', ARGV[9], 'generation', ARGV[10],
    'created_ms', now, 'last_ms', now, 'digest', ARGV[5], 'notice_version', ARGV[2], 'owner', ARGV[1])
redis.call('HSET', KEYS[4], 'profile_draft', ARGV[15], 'profile_evidence', '[]', 'profile_changed', '0', 'role_exclusions', '[]')
if imported_at then
    redis.call('HSET', KEYS[4], 'confirmed_version', 1, 'confirmed_at_ms', imported_at,
        'confirmed:1:content', ARGV[15], 'confirmed:1:at', imported_at)
end
redis.call('PEXPIRE', KEYS[4], ARGV[3])
redis.call('HSET', KEYS[2], 'input', ARGV[7], 'resource', KEYS[3], 'meta', KEYS[4])
redis.call('PEXPIRE', KEYS[2], ARGV[14])
redis.call('HINCRBY', KEYS[5], 'limit:' .. ARGV[13], 1)
return view(KEYS[3], KEYS[4], false)
"""

_LOAD = _SESSION + _VIEW + "return view(KEYS[2], KEYS[3], ARGV[7] == '1')"

_MESSAGE_DATA = _SESSION + _VIEW + """
local state = view(KEYS[2], KEYS[3], false)
if state[1] ~= 'ok' then return state end
local value = redis.call('HGET', KEYS[3], ARGV[7])
if not value then
    if ARGV[7] == 'conversation' then value = '[]' else return {'NOT_FOUND'} end
end
return {'ok', value}
"""

_QUESTION = _SESSION + _VIEW + """
local state = view(KEYS[2], KEYS[3], false)
if state[1] ~= 'ok' then return state end
local count = 0
for _, field in ipairs(redis.call('HKEYS', KEYS[3])) do
    if string.sub(field, 1, 15) == 'message_result:' then
        count = count + 1
        if count > 64 then return {'SERVICE_UNAVAILABLE'} end
        local raw = redis.call('HGET', KEYS[3], field)
        if not raw or string.len(raw) > 65536 then return {'SERVICE_UNAVAILABLE'} end
        local ok, result = pcall(cjson.decode, raw)
        if not ok or type(result) ~= 'table' then return {'SERVICE_UNAVAILABLE'} end
        local question = result.assistant_message
        if type(question) == 'table' and question.message_id == ARGV[7] then return {'ok', cjson.encode(question)} end
    end
end
return {'NOT_FOUND'}
"""

_END = _SESSION_LIFETIME + """
local m = redis.call('HMGET', KEYS[3], 'owner', 'digest')
if m[1] and (m[1] ~= ARGV[1] or m[2] ~= ARGV[5]) then return {'ok'} end
local index = KEYS[2] .. ':requests'
if redis.call('SCARD', index) > tonumber(ARGV[7]) then return {'SERVICE_UNAVAILABLE'} end
for _, key in ipairs(redis.call('SMEMBERS', index)) do redis.call('DEL', key) end
redis.call('DEL', KEYS[2], KEYS[3], index)
return {'ok'}
"""

_PROFILE_RESULT = """
local function profile_result(revision)
    local p = redis.call('HMGET', KEYS[3], 'profile_draft', 'profile_evidence', 'confirmed_version', 'confirmed_at_ms', 'profile_changed')
    if not p[1] or not p[2] or (p[5] ~= '0' and p[5] ~= '1') then return {'SERVICE_UNAVAILABLE'} end
    if (p[3] and not p[4]) or (p[4] and not p[3]) then return {'SERVICE_UNAVAILABLE'} end
    return {'ok', revision, p[1], p[2], p[3] or '', p[4] or '', p[5]}
end
local state = view(KEYS[2], KEYS[3], false)
if state[1] ~= 'ok' then return state end
"""
_PROFILE = _SESSION_LIFETIME + _VIEW + _PROFILE_RESULT + "return profile_result(state[7])"
_UPDATE_PROFILE = _SESSION_LIFETIME + _VIEW + _PROFILE_RESULT + """
if state[7] ~= ARGV[7] then return {'VERSION_CONFLICT'} end
local previous = profile_result(state[7])
if previous[1] ~= 'ok' then return previous end
local changed = previous[5] ~= '' and '1' or '0'
local revision = tonumber(state[7]) + 1
redis.call('HSET', KEYS[3], 'profile_draft', ARGV[8], 'profile_evidence', '[]', 'profile_changed', changed)
redis.call('SET', KEYS[2], 'g:' .. tostring(revision), 'XX', 'KEEPTTL')
view(KEYS[2], KEYS[3], true)
return profile_result(tostring(revision))
"""

_CONFIRM_PROFILE = _SESSION_LIFETIME + _VIEW + _PROFILE_RESULT + """
if state[7] ~= ARGV[7] then return {'VERSION_CONFLICT'} end
local p = profile_result(state[7])
if p[1] ~= 'ok' then return p end
if p[3] ~= ARGV[8] then return {'VERSION_CONFLICT'} end
local previous = p[5] == '' and '0' or p[5]
if not string.match(previous, '^%d+$') then return {'SERVICE_UNAVAILABLE'} end
if p[5] ~= '' and tonumber(previous) < 1 then return {'SERVICE_UNAVAILABLE'} end
local version = tonumber(previous) + 1
if version > tonumber(ARGV[9]) then return {'RATE_LIMITED', tostring(math.max(1, math.ceil(redis.call('PTTL', KEYS[3]) / 1000)))} end
local content_field = 'confirmed:' .. tostring(version) .. ':content'
local time_field = 'confirmed:' .. tostring(version) .. ':at'
if redis.call('HEXISTS', KEYS[3], content_field) == 1 or redis.call('HEXISTS', KEYS[3], time_field) == 1 then return {'SERVICE_UNAVAILABLE'} end
local revision = tonumber(state[7]) + 1
redis.call('HSET', KEYS[3], content_field, p[3], time_field, now,
    'confirmed_version', version, 'confirmed_at_ms', now, 'profile_changed', '0')
redis.call('SET', KEYS[2], 'g:' .. tostring(revision), 'XX', 'KEEPTTL')
view(KEYS[2], KEYS[3], true)
return {'ok', tostring(version), tostring(now), tostring(revision)}
"""

_RESOLVE_PROFILE = _SESSION_LIFETIME + _VIEW + _PROFILE_RESULT + """
local p = profile_result(state[7])
if p[1] ~= 'ok' then return p end
if p[5] == '' then return {'PROFILE_NOT_CONFIRMED'} end
if ARGV[8] == '1' and p[5] ~= ARGV[7] then return {'VERSION_CONFLICT'} end
local content = redis.call('HGET', KEYS[3], 'confirmed:' .. ARGV[7] .. ':content')
local at = redis.call('HGET', KEYS[3], 'confirmed:' .. ARGV[7] .. ':at')
if not content or not at then return {'VERSION_CONFLICT'} end
return {'ok', content, at}
"""

_ROLE_STATE = _SESSION_LIFETIME + _VIEW + """
local state = view(KEYS[2], KEYS[3], false)
if state[1] ~= 'ok' then return state end
if state[8] == '' then return {'PROFILE_NOT_CONFIRMED'} end
return {'ok', state[7], state[8], redis.call('HGET', KEYS[3], 'role_exclusions') or '[]'}
"""

_SET_ROLE_EXCLUSIONS = _SESSION_LIFETIME + _VIEW + """
local state = view(KEYS[2], KEYS[3], false)
if state[1] ~= 'ok' then return state end
if state[8] == '' then return {'PROFILE_NOT_CONFIRMED'} end
if state[7] ~= ARGV[7] then return {'VERSION_CONFLICT'} end
local revision = tonumber(state[7]) + 1
redis.call('HSET', KEYS[3], 'role_exclusions', ARGV[8])
redis.call('SET', KEYS[2], 'g:' .. tostring(revision), 'XX', 'KEEPTTL')
view(KEYS[2], KEYS[3], true)
return {'ok', tostring(revision), ARGV[8]}
"""


class RedisJourneyStore:
    session_transition_managed = True

    def __init__(self, client, *, session_key, resource_key, control_key: str, epoch: UUID,
                 prefix: str = "rc:journey:v1:"):
        self._create = client.register_script(_CREATE)
        self._load = client.register_script(_LOAD)
        self._profile = client.register_script(_PROFILE)
        self._update_profile = client.register_script(_UPDATE_PROFILE)
        self._confirm_profile = client.register_script(_CONFIRM_PROFILE)
        self._resolve_profile = client.register_script(_RESOLVE_PROFILE)
        self._role_state = client.register_script(_ROLE_STATE)
        self._set_role_exclusions = client.register_script(_SET_ROLE_EXCLUSIONS)
        self._end = client.register_script(_END)
        self._message_data = client.register_script(_MESSAGE_DATA)
        self._question = client.register_script(_QUESTION)
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
            status, journey, message, generation, created, last, revision, confirmed_version, confirmed_at = values
            if status != "ok":
                raise ValueError
            created, last = int(created), int(last)
            if not 0 <= created <= last:
                raise ValueError
            def timestamp(value):
                return datetime.fromtimestamp(value / 1000, UTC)
            view = Journey(journey_id=UUID(journey), revision=int(revision), expires_at=timestamp(created + RESOURCE_MAX_MS),
                           idle_expires_at=timestamp(min(last + IDLE_MS, created + RESOURCE_MAX_MS)),
                           first_message=Message(message_id=UUID(message), text=FIRST_QUESTION, created_at=timestamp(created)),
                           confirmed=self._confirmation(confirmed_version, confirmed_at))
            return JourneyRecord(view, CompletionGuard(session.digest, UUID(generation), version))
        except (RedisError, ValueError, TypeError, IndexError, OverflowError, OSError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    async def create(self, session, key_id, fingerprint, notice_version, budget, key_id_digest, *, initial_profile=None, confirmed_at=None):
        if (initial_profile is None) != (confirmed_at is None):
            raise AppError('SERVICE_UNAVAILABLE')
        journey, message, generation = uuid4(), uuid4(), uuid4()
        resource = self.resource_key(session.subject_id, journey)
        journal = self.prefix + hashlib.sha256(f"{session.subject_id}:{key_id}".encode("ascii")).hexdigest()
        return await self._call(self._create,
            [self.session_key(session.digest), journal, resource, resource + ":lifecycle", self.control_key,
             self.session_key(session.digest) + ':journeys'],
            [*self._args(session, notice_version), fingerprint, str(journey), str(message), str(generation),
             str(self.epoch), key_id_digest, budget, RETENTION_MS,
             (initial_profile if initial_profile is not None else empty_profile_content()).model_dump_json(),
             '1' if initial_profile is not None else '0',
             int(confirmed_at.timestamp()) * 1000 + confirmed_at.microsecond // 1000 if confirmed_at else ''], session, notice_version)

    async def load(self, session, journey_id, notice_version, *, user_activity=False):
        resource = self.resource_key(session.subject_id, journey_id)
        return await self._call(self._load, [self.session_key(session.digest), resource, resource + ":lifecycle"],
                                [*self._args(session, notice_version), "1" if user_activity else "0"], session, notice_version)

    async def _profile_call(self, script, session, journey_id, extra=()):
        resource = self.resource_key(session.subject_id, journey_id)
        try:
            values = await script(keys=[self.session_key(session.digest), resource, resource + ":lifecycle"],
                                  args=[*self._args(session, ""), *extra])
            if not isinstance(values, list) or not values:
                raise ValueError
            if values[0] in {"NOT_FOUND", "SERVICE_UNAVAILABLE", "VERSION_CONFLICT"}:
                raise AppError(values[0])
            status, revision, draft_json, evidence_json, confirmed_version, confirmed_at, changed = values
            if status != "ok" or changed not in ("0", "1"):
                raise ValueError
            if len(draft_json.encode("utf-8")) > 65536 or len(evidence_json.encode("utf-8")) > 65536:
                raise ValueError
            draft = ProfileContent.model_validate_json(draft_json)
            if len({item.id for item in draft.experiences}) != len(draft.experiences):
                raise ValueError
            confirmed = self._confirmation(confirmed_version, confirmed_at)
            return ProfileDraftView.model_validate({
                "revision": int(revision), "draft": draft,
                "evidence": json.loads(evidence_json), "confirmed": confirmed,
                "has_unconfirmed_changes": changed == "1", "missing_for_recommendation": draft.missing_for_recommendation(),
            })
        except (RedisError, ValueError, TypeError, OverflowError, OSError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    async def profile(self, session, journey_id):
        return await self._profile_call(self._profile, session, journey_id)

    async def message_data(self, session, journey_id, notice_version, field):
        if field != 'conversation':
            try:
                if field != f'message_result:{UUID(field.removeprefix("message_result:"))}':
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                raise AppError('SERVICE_UNAVAILABLE') from None
        resource = self.resource_key(session.subject_id, journey_id)
        values = await self._call_data(session, resource, notice_version, field)
        return values

    async def question(self, session, journey_id, notice_version, message_id):
        resource = self.resource_key(session.subject_id, journey_id)
        try:
            values = await self._question(keys=[self.session_key(session.digest), resource, resource + ':lifecycle'],
                args=[*self._args(session, notice_version), str(message_id)])
            if values and values[0] in {'NOT_FOUND', 'CONSENT_REQUIRED', 'SERVICE_UNAVAILABLE'}:
                raise AppError(values[0])
            if len(values) != 2 or values[0] != 'ok' or len(values[1].encode('utf-8')) > 16384:
                raise ValueError
            result = Message.model_validate_json(values[1])
            if result.message_id != message_id:
                raise ValueError
            return result
        except (RedisError, ValueError, TypeError, AttributeError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def _call_data(self, session, resource, notice_version, field):
        try:
            values = await self._message_data(keys=[self.session_key(session.digest), resource, resource + ':lifecycle'],
                args=[*self._args(session, notice_version), field])
            if values and values[0] in {'NOT_FOUND', 'CONSENT_REQUIRED', 'SERVICE_UNAVAILABLE'}:
                raise AppError(values[0])
            if not isinstance(values, list) or len(values) != 2 or values[0] != 'ok' or len(values[1].encode('utf-8')) > 131072:
                raise ValueError
            return values[1]
        except (RedisError, ValueError, TypeError, AttributeError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    async def end(self, session, journey_id):
        values = await self._version_call(self._end, session, journey_id, (MAX_RESOURCE_REQUESTS,))
        if values != ['ok']:
            raise AppError('SERVICE_UNAVAILABLE')

    async def update_profile(self, session, journey_id, draft, base_revision):
        return await self._profile_call(self._update_profile, session, journey_id, (base_revision, draft.model_dump_json()))

    @staticmethod
    def _confirmation(version, at):
        if not version and not at:
            return None
        return ConfirmedVersion(version=int(version), confirmed_at=datetime.fromtimestamp(int(at) / 1000, UTC))

    async def _version_call(self, script, session, journey_id, extra):
        resource = self.resource_key(session.subject_id, journey_id)
        try:
            values = await script(keys=[self.session_key(session.digest), resource, resource + ":lifecycle"],
                                  args=[*self._args(session, ""), *extra])
            if not isinstance(values, list) or not values:
                raise ValueError
            if values[0] in {"NOT_FOUND", "SERVICE_UNAVAILABLE", "VERSION_CONFLICT", "PROFILE_NOT_CONFIRMED"}:
                raise AppError(values[0])
            if values[0] == "RATE_LIMITED":
                raise AppError("RATE_LIMITED", retry_after=int(values[1]))
            if values[0] != "ok":
                raise ValueError
            return values
        except (RedisError, ValueError, TypeError, IndexError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    async def confirm_profile(self, session, journey_id, draft, base_revision):
        missing = draft.missing_for_recommendation()
        if missing:
            raise MissingProfileFields(missing)
        values = await self._version_call(self._confirm_profile, session, journey_id,
                                          (base_revision, draft.model_dump_json(), MAX_CONFIRMED_VERSIONS))
        try:
            _, version, at, revision = values
            confirmation = self._confirmation(version, at)
            return ProfileConfirmResult(profile=ProfileRef(kind="journey", id=journey_id, version=confirmation.version),
                                        confirmed_at=confirmation.confirmed_at, revision=int(revision))
        except (ValueError, TypeError, OverflowError, OSError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    async def resolve_profile(self, session, reference, *, require_current=False):
        values = await self._version_call(self._resolve_profile, session, reference.id,
                                          (reference.version, "1" if require_current else "0"))
        try:
            _, content, at = values
            if len(content.encode("utf-8")) > 65536:
                raise ValueError
            profile = ProfileContent.model_validate_json(content)
            if profile.missing_for_recommendation() or len({e.id for e in profile.experiences}) != len(profile.experiences):
                raise ValueError
            confirmation = self._confirmation(reference.version, at)
            return ResolvedJourneyProfile(reference, profile, confirmation.confirmed_at)
        except (ValueError, TypeError, OverflowError, OSError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    async def role_state(self, session, journey_id):
        values = await self._version_call(self._role_state, session, journey_id, ())
        try:
            _, revision, version, encoded = values
            if len(encoded.encode("utf-8")) > 65536 or not 1 <= int(version) <= MAX_CONFIRMED_VERSIONS:
                raise ValueError
            exclusions = RoleExclusions(role_ids=json.loads(encoded), revision=int(revision))
            return RoleState(exclusions.revision, int(version), tuple(exclusions.role_ids))
        except (ValueError, TypeError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None

    async def set_role_exclusions(self, session, journey_id, role_ids, base_revision):
        try:
            validated = RoleExclusionUpdate(role_ids=role_ids, base_revision=base_revision)
        except ValidationError:
            raise AppError("VALIDATION_FAILED") from None
        values = await self._version_call(self._set_role_exclusions, session, journey_id,
                                          (validated.base_revision, json.dumps(validated.role_ids, ensure_ascii=True, separators=(",", ":"))))
        try:
            _, revision, encoded = values
            return RoleExclusions(role_ids=json.loads(encoded), revision=int(revision))
        except (ValueError, TypeError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None
