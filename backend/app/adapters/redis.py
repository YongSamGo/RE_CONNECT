"""Redis 연결·상태 확인. 체험 데이터의 영속화 설정도 함께 확인한다."""

from redis.asyncio import Redis
from urllib.parse import urlsplit

from app.core.config import Settings


def build_redis(settings: Settings) -> Redis:
    if settings.redis_url is None:
        raise ValueError("Redis 연결 설정이 필요합니다")
    value = settings.redis_url.get_secret_value()
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("redis", "rediss") or not parsed.hostname or parsed.query or parsed.fragment:
            raise ValueError
        return Redis.from_url(value, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)
    except ValueError:
        raise ValueError("Redis 연결 설정 형식 오류") from None


class RedisProbe:
    def __init__(self, client: Redis):
        self.client = client

    async def is_ready(self) -> bool:
        try:
            if not await self.client.ping():
                return False
            persistence = await self.client.config_get("save", "appendonly")
            return persistence.get("save") == "" and persistence.get("appendonly") == "no"
        except Exception:
            return False
