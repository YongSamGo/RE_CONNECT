"""업무 오류는 허용한 코드·고정 문구·서버 추적 ID만 반환한다."""

from pathlib import Path

import pytest
from fastapi import FastAPI

from app.core.business_errors import ERRORS, AppError
from app.main import create_app


@pytest.mark.parametrize("code", ERRORS)
def test_every_business_error_has_fixed_status_message_and_no_cache(code, make_client, test_settings):
    app = create_app(test_settings)
    retry = 10 if code == "REQUEST_IN_PROGRESS" or ERRORS[code].status == 429 else None

    @app.post("/business")
    async def business():
        raise AppError(code, retry_after=retry)

    response = make_client(app).post("/business?code=secret-code&state=secret-state", json={"otp": "private-otp", "text": "private-body"})
    body = response.json()
    assert response.status_code == ERRORS[code].status
    assert body["code"] == code
    assert body["message"] == ERRORS[code].message
    assert body["request_id"] == response.headers["x-request-id"]
    assert set(body) == {"code", "message", "request_id"} | ({"fields"} if code == "VALIDATION_FAILED" else set())
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get("retry-after") == (str(retry) if retry else None)
    for secret in ("secret-code", "secret-state", "private-otp", "private-body"):
        assert secret not in response.text


def test_business_registry_matches_api_contract():
    # 표준 라이브러리로 이 enum 블록만 대조해 불필요한 YAML 런타임 의존성을 피한다.
    text = (Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml").read_text(encoding="utf-8")
    block = text.split("    ErrorCode:\n", 1)[1].split("    Error:\n", 1)[0]
    codes = {line.strip()[2:] for line in block.splitlines() if line.strip().startswith("- ")}
    assert set(ERRORS) == codes


@pytest.mark.parametrize("code,retry", [
    ("private-token", None), ("REQUEST_IN_PROGRESS", None),
    ("RATE_LIMITED", True), ("RATE_LIMITED", 0), ("RATE_LIMITED", 86401),
    ("RATE_LIMITED", "10\r\nX-Leak: token"), ("NOT_FOUND", 10),
])
def test_unknown_codes_and_invalid_retry_headers_are_rejected(code, retry):
    with pytest.raises(ValueError):
        AppError(code, retry_after=retry)


def test_inaccessible_and_absent_resources_share_private_not_found(make_client, test_settings):
    app: FastAPI = create_app(test_settings)

    @app.get("/private/{resource}")
    async def private(resource: str):
        raise AppError("NOT_FOUND")

    client = make_client(app)
    first, second = [client.get(f"/private/{value}") for value in ("absent", "other-owner")]
    assert first.status_code == second.status_code == 404
    assert first.json()["message"] == second.json()["message"]
