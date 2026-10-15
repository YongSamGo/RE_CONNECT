import logging

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.main import create_app
from tests.conftest import ready_probes

ERROR_KEYS = {"code", "message", "request_id"}
SECRET_MESSAGE = "postgresql://admin:SuperSecret@db/reconnect token=secret-token /srv/app/main.py"


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
        raise RuntimeError(SECRET_MESSAGE)

    @router.get("/http-error/{status_code}")
    async def http_error(status_code: int) -> None:
        raise HTTPException(status_code=status_code, detail=SECRET_MESSAGE, headers={"Retry-After": "30"})

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
    for leaked in ("postgresql", "SuperSecret", "secret-token", "/srv/app", "RuntimeError", "Traceback"):
        assert leaked not in response.text


def test_unhandled_exception_is_not_reraised_to_server(
    test_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    # 예외가 서버(uvicorn)까지 올라가면 메시지·traceback 전체가 서버 로그에 남는다.
    client = TestClient(app_with_sample_routes(test_settings), raise_server_exceptions=True)

    with caplog.at_level(logging.DEBUG):
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "RuntimeError" in caplog.text
    assert response.headers["x-request-id"] in caplog.text
    for leaked in ("postgresql", "SuperSecret", "secret-token", "/srv/app"):
        assert leaked not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize(
    ("raised", "status_code", "code"),
    [
        (400, 422, "VALIDATION_FAILED"),
        (401, 401, "UNAUTHENTICATED"),
        (403, 403, "FORBIDDEN"),
        (404, 404, "NOT_FOUND"),
        (405, 404, "NOT_FOUND"),
        (413, 413, "PAYLOAD_TOO_LARGE"),
        (415, 422, "VALIDATION_FAILED"),
        (429, 429, "RATE_LIMITED"),
        (500, 500, "INTERNAL_ERROR"),
        (503, 500, "INTERNAL_ERROR"),
    ],
)
def test_http_exceptions_keep_client_errors_as_4xx(
    make_client, test_settings: Settings, raised: int, status_code: int, code: str
) -> None:
    client = make_client(app_with_sample_routes(test_settings))

    response = client.get(f"/http-error/{raised}")

    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert "SuperSecret" not in response.text
    # Retry-After는 429에만 넘긴다.
    assert ("retry-after" in response.headers) == (status_code == 429)


def test_unknown_field_name_is_not_reflected(make_client, test_settings: Settings) -> None:
    client = make_client(app_with_sample_routes(test_settings))

    response = client.post(
        "/sample",
        json={"name": "a", "age": 1, "tags": [], "<script>alert(1)</script>": 1, "주민번호_620315": 2},
    )

    assert response.status_code == 422
    assert response.json()["fields"] == [
        {"path": "<unknown>", "reason": "unknown_field"},
        {"path": "<unknown>", "reason": "unknown_field"},
    ]
    assert "script" not in response.text
    assert "620315" not in response.text


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (None, "required"),
        ("[1]", "invalid_type"),
        ("{bad", "invalid_value"),
    ],
)
def test_whole_body_errors_point_to_body(
    make_client, test_settings: Settings, content: str | None, reason: str
) -> None:
    client = make_client(app_with_sample_routes(test_settings))

    response = client.post("/sample", content=content, headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert response.json()["fields"] == [{"path": "body", "reason": reason}]
