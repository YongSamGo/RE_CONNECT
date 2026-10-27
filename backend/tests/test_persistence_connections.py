"""접속 설정 비노출·운영 TLS·실제 연결 상태와 Redis 비영속화 검사."""

import asyncio
import os

import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient

from app.adapters.redis import RedisProbe, build_redis
from app.core.config import Settings
from app.persistence.connection import DatabaseProbe, build_engine, database_url
from app.main import create_app
from tests.conftest import FakeProbe


def settings(**updates):
    return Settings(_env_file=None, app_env="test", **updates)


def test_connection_credentials_are_secret_in_settings_repr():
    configured = settings(database_url="postgresql+psycopg://test:private-db-secret@localhost/test", redis_url="redis://:private-redis-secret@localhost/0")
    assert "private-" not in repr(configured)
    assert isinstance(configured.database_url, SecretStr)


@pytest.mark.parametrize("url", [
    "sqlite:///private-token", "not-a-url-private-token",
    "postgresql://user:private-token@db/test", "postgresql+psycopg:///test",
])
def test_invalid_database_settings_fail_without_reflecting_url(url):
    with pytest.raises(ValueError) as caught:
        database_url(settings(database_url=url))
    assert "private-token" not in str(caught.value)


def test_production_requires_ca_and_hostname_verification():
    for query in ("", "?sslmode=require", "?sslmode=verify-full"):
        configured = Settings(_env_file=None, app_env="production", database_url="postgresql+psycopg://user:private-token@db/test" + query)
        with pytest.raises(ValueError):
            database_url(configured)
    configured = Settings(_env_file=None, app_env="production", database_url="postgresql+psycopg://user:private-token@db/test?sslmode=verify-full&sslrootcert=/run/rds-ca.pem")
    assert database_url(configured).query["sslmode"] == "verify-full"


@pytest.mark.parametrize("url", ["unix:///private-socket", "redis://localhost?socket_timeout=999", "https://private-token@localhost", "redis://localhost#private-token"])
def test_redis_only_accepts_expected_connection_scheme(url):
    with pytest.raises(ValueError) as caught:
        build_redis(settings(redis_url=url))
    assert "private-token" not in str(caught.value)


def test_real_postgresql_and_redis_probes():
    db_url = os.environ.get("PERSISTENCE_TEST_DATABASE_URL")
    redis_url = os.environ.get("PERSISTENCE_TEST_REDIS_URL")
    if not db_url or not redis_url:
        pytest.skip("실제 PostgreSQL/Redis는 CI 통합 잡에서 실행")
    configured = settings(database_url=db_url, redis_url=redis_url)
    engine = build_engine(configured)
    client = build_redis(configured)

    async def check():
        try:
            assert await DatabaseProbe(engine).is_ready()
            assert await RedisProbe(client).is_ready()
            await client.config_set("save", "60 1")
            assert not await RedisProbe(client).is_ready()
            await client.config_set("save", "")
        finally:
            await client.config_set("save", "")
            await client.aclose()

    try:
        asyncio.run(check())
    finally:
        engine.dispose()

    app = create_app(configured, {"llm": FakeProbe(False), "speech": FakeProbe(False)})
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"
        assert response.json()["checks"]["db"] == response.json()["checks"]["redis"] == "ok"
        assert client.get("/api/v1/regions").status_code == 200


def test_database_probe_failure_does_not_log_connection_details(caplog):
    class FailedEngine:
        def connect(self):
            raise RuntimeError("postgresql://private-token@private-host/test")

    assert asyncio.run(DatabaseProbe(FailedEngine()).is_ready()) is False
    assert "private-" not in caplog.text
