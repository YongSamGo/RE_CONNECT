"""단일 Redis 세션 교체의 자료 정리. 삭제 전에 모든 경계를 검사한다."""

MAX_SESSION_JOURNEYS = 60

_CLEANUP_PLAN = """
if redis.call('SCARD', KEYS[6]) > 60 then return redis.error_reply('Invalid journey index') end
local resources = redis.call('SMEMBERS', KEYS[6])
local deletions, cleaned_journeys = {}, 0
for _, resource in ipairs(resources) do
    local meta = resource .. ':lifecycle'
    local owner = redis.call('HMGET', meta, 'owner', 'digest')
    if owner[1] and (owner[1] ~= s[1] or owner[2] ~= ARGV[7]) then
        return redis.error_reply('Invalid journey owner')
    end
    if owner[1] then cleaned_journeys = cleaned_journeys + 1 end
    local requests = resource .. ':requests'
    if redis.call('SCARD', requests) > 256 then return redis.error_reply('Invalid request index') end
    for _, key in ipairs(redis.call('SMEMBERS', requests)) do table.insert(deletions, key) end
    table.insert(deletions, resource)
    table.insert(deletions, meta)
    table.insert(deletions, requests)
end
"""

_CLEANUP_COMMIT = """
for _, key in ipairs(deletions) do redis.call('DEL', key) end
redis.call('DEL', KEYS[6])
"""
