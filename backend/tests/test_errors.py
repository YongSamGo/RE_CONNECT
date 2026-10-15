from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.main import create_app
from tests.conftest import ready_probes

ERROR_KEYS = {"code", "message", "request_id"}


class SampleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=5)
    age: int = Field(ge=0)
    tags: list[str]


def app_with_sample_routes(settings: Settings) -> FastAPI:
    app = create_app(settings, ready_probes())
    router = APIRouter()

    @router.post("/sample")
    async def sample(body: SampleBody) -> dict[str, str]:
        return {"name": body.name}

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("SELECT * FROM users WHERE token='secret-token' /srv/app/main.py")

    app.include_router(router)
    return app


def test_unknown_path_is_contract_404(client: TestClient) -> None:
    response = client.get("/no-such-path")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["code"] == "NOT_FOUND"
    assert body["request_id"] == response.headers["x-request-id"]


def test_wrong_method_looks_like_404(client: TestClient) -> None:
    response = client.post("/health/live")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert "allow" not in response.headers


def test_validation_error_has_fields_without_input(make_client, test_settings: Settings) -> None:
    client = make_client(app_with_sample_routes(test_settings))

    response = client.post(
        "/sample",
        json={"name": "too-long-name<script>", "age": -1, "tags": ["a", 3], "role": "admin"},
    )

    assert response.status_code == 422
    body = response.json()
    assert set(body) == ERROR_KEYS | {"fields"}
    assert body["code"] == "VALIDATION_FAILED"
    assert body["request_id"] == response.headers["x-request-id"]
    reasons = {field["path"]: field["reason"] for field in body["fields"]}
    assert reasons == {
        "name": "too_long",
        "age": "out_of_range",
        "tags[1]": "invalid_type",
        "role": "unknown_field",
    }
    # 입력값과 Pydantic 원문 메시지는 돌려주지 않는다.
    assert "<script>" not in response.text
    assert "admin" not in response.text
    assert "String should" not in response.text


def test_missing_field_is_required(make_client, test_settings: Settings) -> None:
    client = make_client(app_with_sample_routes(test_settings))

    response = client.post("/sample", json={"name": "a", "age": 1})

    assert response.json()["fields"] == [{"path": "tags", "reason": "required"}]


def test_field_errors_are_capped(make_client, test_settings: Settings) -> None:
    client = make_client(app_with_sample_routes(test_settings))
    extra = {f"unknown_{i}": i for i in range(80)}

    response = client.post("/sample", json={"name": "a", "age": 1, "tags": [], **extra})

    assert response.status_code == 422
    assert len(response.json()["fields"]) == 50


def test_unhandled_exception_hides_details(make_client, test_settings: Settings) -> None:
    client = make_client(app_with_sample_routes(test_settings))

    response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["code"] == "INTERNAL_ERROR"
    assert body["request_id"] == response.headers["x-request-id"]
    for leaked in ("SELECT", "secret-token", "/srv/app", "RuntimeError", "Traceback"):
        assert leaked not in response.text
