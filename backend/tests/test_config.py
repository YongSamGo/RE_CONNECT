import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import ready_probes


def settings_for(app_env: str) -> Settings:
    return Settings(_env_file=None, app_env=app_env)  # type: ignore[call-arg]


def test_default_env_is_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)

    assert Settings(_env_file=None).app_env == "production"  # type: ignore[call-arg]


def test_unknown_env_is_rejected() -> None:
    with pytest.raises(ValueError):
        settings_for("staging")


@pytest.mark.parametrize("app_env", ["production", "test"])
def test_api_docs_are_closed_outside_development(app_env: str) -> None:
    client = TestClient(create_app(settings_for(app_env), ready_probes()))

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_api_docs_open_in_development() -> None:
    client = TestClient(create_app(settings_for("development"), ready_probes()))

    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
