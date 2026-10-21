"""회원의 제한된 세션 인덱스와 파생 자원을 같은 Redis 실행에서 정리한다."""

from redis.exceptions import RedisError

from app.modules.sessions.service import StoreUnavailable

_REVOKE = """
if redis.call('SCARD', KEYS[1]) > 16 then return redis.error_reply('Invalid member index') end
local deletions, journeys = {}, 0
local digests = redis.call('SMEMBERS', KEYS[1])
if ARGV[4] and ARGV[4] ~= '' then digests = {ARGV[4]} end
for _, digest in ipairs(digests) do
    if #digest ~= 64 or string.find(digest, '[^0-9a-f]') then return redis.error_reply('Invalid session reference') end
    local session = ARGV[2] .. digest
    local user = redis.call('HGET', session, 'user_id')
    if user and user ~= ARGV[1] then return redis.error_reply('Invalid member owner') end
    local index = session .. ':journeys'
    if redis.call('SCARD', index) > 60 then return redis.error_reply('Invalid journey index') end
    for _, resource in ipairs(redis.call('SMEMBERS', index)) do
        local meta, requests = resource .. ':lifecycle', resource .. ':requests'
        local owner = redis.call('HGET', meta, 'digest')
        if owner and owner ~= digest then return redis.error_reply('Invalid journey owner') end
        if redis.call('SCARD', requests) > 256 then return redis.error_reply('Invalid request index') end
        for _, key in ipairs(redis.call('SMEMBERS', requests)) do table.insert(deletions, key) end
        if owner then journeys = journeys + 1 end
        table.insert(deletions, resource); table.insert(deletions, meta); table.insert(deletions, requests)
    end
    table.insert(deletions, index); table.insert(deletions, session .. ':save-intent')
    table.insert(deletions, ARGV[3] .. digest); table.insert(deletions, session)
end
-- 모든 소유권/개수 검사가 끝난 뒤에만 삭제한다.
for _, key in ipairs(deletions) do redis.call('DEL', key) end
if ARGV[4] and ARGV[4] ~= '' then redis.call('SREM', KEYS[1], ARGV[4]) else redis.call('DEL', KEYS[1]) end
return journeys
"""


class RedisMemberCleanup:
    def __init__(self, store):
        self.store = store
        self.script = store.client.register_script(_REVOKE)

    async def revoke(self, user_id):
        return await self._revoke(user_id, '')

    async def revoke_one(self, user_id, digest):
        return await self._revoke(user_id, self.store._digest(digest))

    async def _revoke(self, user_id, digest):
        try:
            return int(await self.script(keys=[self.store.member_prefix + str(user_id) + ':sessions'],
                args=[str(user_id), self.store.session_prefix, self.store.flow_prefix, digest]))
        except (RedisError, ValueError, TypeError):
            raise StoreUnavailable from None


class UnavailableMemberCleanup:
    async def revoke(self, *args):
        raise StoreUnavailable
