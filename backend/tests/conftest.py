from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.operations.readiness import COMPONENTS, Component, ReadinessProbe


class FakeProbe:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready

    async def is_ready(self) -> bool:
        return self.ready


def ready_probes(**overrides: ReadinessProbe) -> dict[Component, ReadinessProbe]:
    probes: dict[Component, ReadinessProbe] = {component: FakeProbe() for component in COMPONENTS}
    probes.update(overrides)  # type: ignore[arg-type]
    return probes


@pytest.fixture
def test_settings() -> Settings:
    # 저장소의 .env 값에 영향받지 않게 파일을 읽지 않는다.
    return Settings(_env_file=None, app_env="test", health_check_timeout_seconds=0.2)  # type: ignore[call-arg]


@pytest.fixture
def make_client(test_settings: Settings) -> Callable[..., TestClient]:
    def _make(app: FastAPI | None = None, **probe_overrides: ReadinessProbe) -> TestClient:
        app = app or create_app(test_settings, ready_probes(**probe_overrides))
        # 500 처리기를 확인할 수 있게 서버 예외를 테스트로 다시 던지지 않는다.
        return TestClient(app, raise_server_exceptions=False)

    return _make


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()
