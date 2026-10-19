"""PostgreSQL 접속과 readiness. 연결 실패 원문·URL·SQL 파라미터를 노출하지 않는다."""

import asyncio

from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings


def database_url(settings: Settings) -> URL:
    if settings.database_url is None:
        raise ValueError("DB 연결 설정이 필요합니다")
    try:
        url = make_url(settings.database_url.get_secret_value())
    except Exception:
        raise ValueError("DB 연결 설정 형식 오류") from None
    if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
        raise ValueError("PostgreSQL psycopg 연결만 허용합니다")
    if settings.app_env == "production":
        if url.query.get("sslmode") != "verify-full" or not url.query.get("sslrootcert"):
            raise ValueError("운영 DB는 CA·호스트 검증 TLS 설정이 필요합니다")
    return url


def build_engine(settings: Settings, **options):
    return create_engine(
        database_url(settings), echo=False, hide_parameters=True,
        pool_pre_ping=True, connect_args={"connect_timeout": 2}, **options,
    )


class DatabaseProbe:
    def __init__(self, engine):
        self.engine = engine

    def _check(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def is_ready(self) -> bool:
        return await asyncio.to_thread(self._check)
