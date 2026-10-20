"""실제 Redis TIME/세션 수명으로 제한하는 최대 3개 일회 OAuth state."""

import json
import re
from uuid import UUID

from redis.exceptions import RedisError

from app.modules.auth.service import Flow
from app.modules.sessions.service import ABSOLUTE_MS, IDLE_MS, StoreUnavailable

_SCRIPT = """
local s = redis.call('HMGET', KEYS[1], 'created_ms', 'last_ms')
if not s[1] then return nil end
local t = redis.call('TIME')
local now = tonumber(t[1])*1000 + math.floor(tonumber(t[2])/1000)
local created, last = tonumber(s[1]), tonumber(s[2])
if not created or not last or last < created or now < last then return redis.error_reply('Invalid session state') end
local remaining = math.min(created + tonumber(ARGV[4]) - now, last + tonumber(ARGV[3]) - now)
if remaining <= 0 then return nil end
if redis.call('LLEN', KEYS[2]) > 3 then return redis.error_reply('Invalid flow state') end
local values = redis.call('LRANGE', KEYS[2], 0, 2)
local live, result = {}, nil
for _, raw in ipairs(values) do
    local v = cjson.decode(raw)
    if v.expires > now then
        if ARGV[1] == 'consume' and v.digest == ARGV[2] then result = v.payload
        else table.insert(live, raw) end
    end
end
if ARGV[1] == 'create' then
    for _, raw in ipairs(live) do if cjson.decode(raw).digest == ARGV[2] then return nil end end
    while #live >= 3 do table.remove(live, 1) end
    table.insert(live, cjson.encode({digest=ARGV[2],expires=now+math.min(600000,remaining),payload=ARGV[5]}))
    result = 'created'
end
redis.call('DEL', KEYS[2])
if #live > 0 then
    for _, raw in ipairs(live) do redis.call('RPUSH', KEYS[2], raw) end
    redis.call('PEXPIRE', KEYS[2], math.min(600000, remaining))
end
return result
"""


class RedisFlowStore:
    def __init__(self, client, *, session_prefix="rc:session:v1:", prefix="rc:oauth:v1:"):
        self.client, self.session_prefix, self.prefix = client, session_prefix, prefix
        self.script = client.register_script(_SCRIPT)

    async def _run(self, session_digest, digest, action, payload=""):
        if any(not isinstance(v, str) or re.fullmatch(r"[0-9a-f]{64}", v) is None for v in (session_digest, digest)):
            raise StoreUnavailable
        try:
            return await self.script(keys=[self.session_prefix + session_digest, self.prefix + session_digest],
                args=[action, digest, IDLE_MS, ABSOLUTE_MS, payload])
        except RedisError:
            raise StoreUnavailable from None

    async def create(self, session_digest, digest, flow):
        return await self._run(session_digest, digest, "create", json.dumps({"purpose": flow.purpose, "verifier": flow.verifier,
            **({'save_intent_id': flow.save_intent_id} if flow.save_intent_id is not None else {})})) == "created"

    async def consume(self, session_digest, digest):
        raw = await self._run(session_digest, digest, "consume")
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            if set(value) not in ({"purpose", "verifier"}, {"purpose", "verifier", "save_intent_id"}) or value["purpose"] not in {"login", "save", "reauth"} or re.fullmatch(r"[A-Za-z0-9_-]{43}", value["verifier"]) is None:
                raise ValueError
            reference = value.get('save_intent_id')
            if reference is not None and (not isinstance(reference, str) or value['purpose'] != 'save' or str(UUID(reference)) != reference):
                raise ValueError
            return Flow(**value)
        except (ValueError, TypeError):
            raise StoreUnavailable from None
