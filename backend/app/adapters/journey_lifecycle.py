"""단일 Redis 체험 저장소들이 공유하는 소유권·수명 Lua. 서비스 의존성은 없다."""

_SESSION_LIFETIME = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local s = redis.call('HMGET', KEYS[1], 'subject_id', 'created_ms', 'last_ms', 'ai_notice_version', 'ai_granted_ms')
if not s[1] or s[1] ~= ARGV[1] or redis.call('PTTL', KEYS[1]) <= 0 then return {'NOT_FOUND'} end
local sc, sl, granted = tonumber(s[2]), tonumber(s[3]), tonumber(s[5])
if not sc or not sl or sl < sc or now < sl then return {'SERVICE_UNAVAILABLE'} end
if now >= sc + tonumber(ARGV[4]) or now >= sl + tonumber(ARGV[3]) then return {'NOT_FOUND'} end
"""
_VIEW = """
local function view(resource, meta, touch)
    local r = redis.call('HMGET', meta, 'journey_id', 'first_message_id', 'generation', 'created_ms', 'last_ms', 'digest', 'notice_version', 'owner')
    if not r[1] or not r[2] or not r[3] or not r[7] or r[6] ~= ARGV[5] or (ARGV[2] ~= '' and r[7] ~= ARGV[2]) or r[8] ~= ARGV[1] then return {'NOT_FOUND'} end
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
    local c = redis.call('HMGET', meta, 'confirmed_version', 'confirmed_at_ms')
    return {'ok', r[1], r[2], r[3], r[4], r[5], string.sub(revision, 3), c[1] or '', c[2] or ''}
end
"""
