import asyncio

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import FakeProbe


class SlowProbe:
    async def is_ready(self) -> bool:
        await asyncio.sleep(5)
        return True


class BrokenProbe:
    async def is_ready(self) -> bool:
        raise ConnectionError("postgresql://reconnect:secret@db:5432 연결 실패")


class TruthyProbe:
    async def is_ready(self) -> object:
        return "yes"


def test_live_returns_ok(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_when_all_components_ok(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"db": "ok", "redis": "ok", "llm": "ok", "speech": "ok"},
    }
    assert response.headers["cache-control"] == "no-store"


def test_ai_failure_degrades_but_stays_200(make_client) -> None:
    response = make_client(llm=FakeProbe(ready=False)).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "checks": {"db": "ok", "redis": "ok", "llm": "fail", "speech": "ok"},
    }


def test_speech_failure_degrades_but_stays_200(make_client) -> None:
    response = make_client(speech=FakeProbe(ready=False)).get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_redis_failure_is_unavailable(make_client) -> None:
    response = make_client(redis=FakeProbe(ready=False)).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"db": "ok", "redis": "fail", "llm": "ok", "speech": "ok"},
    }


def test_db_failure_is_unavailable(make_client) -> None:
    response = make_client(db=FakeProbe(ready=False), llm=FakeProbe(ready=False)).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


def test_probe_exception_is_fail_without_details(make_client) -> None:
    response = make_client(db=BrokenProbe()).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["db"] == "fail"
    # 연결 문자열·오류 메시지가 응답으로 새지 않는다.
    assert "secret" not in response.text
    assert "postgresql" not in response.text


def test_probe_timeout_is_fail(make_client) -> None:
    response = make_client(llm=SlowProbe()).get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["llm"] == "fail"


def test_probe_must_return_true_exactly(make_client) -> None:
    response = make_client(speech=TruthyProbe()).get("/health/ready")

    assert response.json()["checks"]["speech"] == "fail"


def test_unconfigured_components_are_not_reported_ok(test_settings: Settings) -> None:
    # 연결 구현이 없는 기본 상태를 정상으로 꾸미지 않는다.
    client = TestClient(create_app(test_settings))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"db": "fail", "redis": "fail", "llm": "fail", "speech": "fail"},
    }


def test_health_is_not_under_public_api_prefix(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").status_code == 404
    assert client.get("/api/v1/health/ready").status_code == 404
