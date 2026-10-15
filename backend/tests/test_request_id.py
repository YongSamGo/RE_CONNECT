import re

import pytest
from fastapi.testclient import TestClient

# docs/api/openapi.yaml components.headers.XRequestId
REQUEST_ID_PATTERN = re.compile(r"^req_[0-9A-Za-z]{10,32}$")


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/no-such-path"])
def test_every_response_has_one_request_id(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert len(response.headers.get_list("x-request-id")) == 1
    assert REQUEST_ID_PATTERN.fullmatch(response.headers["x-request-id"])


def test_request_ids_are_unique(client: TestClient) -> None:
    ids = {client.get("/health/live").headers["x-request-id"] for _ in range(20)}

    assert len(ids) == 20


@pytest.mark.parametrize("supplied", ["req_AAAAAAAAAAAA", "req_forged <script>alert(1)</script>"])
def test_client_supplied_request_id_is_ignored(client: TestClient, supplied: str) -> None:
    response = client.get("/no-such-path", headers={"X-Request-ID": supplied})

    assert response.headers.get_list("x-request-id") != [supplied]
    assert REQUEST_ID_PATTERN.fullmatch(response.headers["x-request-id"])
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "forged" not in response.text
