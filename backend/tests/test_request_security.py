"""CSRF/Origin·실제 ASGI 스트림 제한·캐시·신뢰 프록시 경계를 검증한다."""

import asyncio
import json

from fastapi import Request
from fastapi.testclient import TestClient
import httpx
from pydantic import ValidationError
import pytest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import Settings, canonical_origin
from app.main import create_app
from app.modules.sessions.service import SessionService, StoreUnavailable
from tests.test_sessions import FakeStore

ORIGIN = "https://testserver"


def secure_app(origin=ORIGIN):
    app = create_app(Settings(_env_file=None, app_env="test", public_origin=origin))
    store = FakeStore()
    app.state.session_service = SessionService(store)
    called = []

    @app.post("/api/v1/change")
    async def change(body: dict):
        called.append(body)
        return {"value": len(body.get("value", ""))}

    @app.get("/api/v1/private-read")
    async def private():
        return {"fictional": True}

    @app.get("/api/v1/read-bytes")
    async def read_bytes(request: Request):
        return {"length": len(await request.body())}

    return app, store, called


def headers(client):
    return {"Origin": ORIGIN, "X-CSRF-Token": client.cookies.get("__Host-rc_csrf")}


def test_valid_request_reaches_handler_and_private_responses_have_no_store():
    app, _, called = secure_app()
    with TestClient(app, base_url=ORIGIN) as client:
        client.get("/api/v1/me")
        response = client.post("/api/v1/change", json={"value": "ok"}, headers=headers(client))
        assert response.status_code == 200
        assert called == [{"value": "ok"}]
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/api/v1/private-read").headers["cache-control"] == "no-store"


@pytest.mark.parametrize("origin", [None, "null", "https://attacker.test", "https://testserver.attacker.test", "https://testserver/path", "https://testserver?", "https://testserver#", "https://testserver,https://attacker.test"])
def test_missing_forged_or_non_origin_values_are_rejected(origin):
    app, _, called = secure_app()
    with TestClient(app, base_url=ORIGIN) as client:
        client.get("/api/v1/me")
        supplied = headers(client)
        if origin is None:
            supplied.pop("Origin")
        else:
            supplied["Origin"] = origin
        response = client.post("/api/v1/change", json={}, headers=supplied)
        assert response.status_code == 403 and response.json()["code"] == "CSRF_FAILED"
        assert called == []


@pytest.mark.parametrize("mode", ["missing", "forged", "other-session", "duplicate-header", "duplicate-origin", "duplicate-cookie"])
def test_csrf_cookie_header_and_signature_are_all_required(mode):
    app, _, called = secure_app()
    with TestClient(app, base_url=ORIGIN) as client:
        client.get("/api/v1/me")
        supplied = list(headers(client).items())
        if mode == "missing":
            supplied = [(key, value) for key, value in supplied if key != "X-CSRF-Token"]
        elif mode == "forged":
            supplied = [("Origin", ORIGIN), ("X-CSRF-Token", "forged")]
        elif mode == "other-session":
            other = TestClient(app, base_url=ORIGIN)
            other.get("/api/v1/me")
            supplied = [("Origin", ORIGIN), ("X-CSRF-Token", other.cookies.get("__Host-rc_csrf")), ("Cookie", f"__Host-rc_session={client.cookies.get('__Host-rc_session')}; __Host-rc_csrf={other.cookies.get('__Host-rc_csrf')}")]
        elif mode == "duplicate-header":
            supplied.append(("X-CSRF-Token", client.cookies.get("__Host-rc_csrf")))
        elif mode == "duplicate-origin":
            supplied.append(("Origin", ORIGIN))
        else:
            csrf = client.cookies.get("__Host-rc_csrf")
            supplied.append(("Cookie", f"__Host-rc_session={client.cookies.get('__Host-rc_session')}; __Host-rc_csrf={csrf}; __Host-rc_csrf={csrf}"))
        assert client.post("/api/v1/change", json={}, headers=supplied).status_code == 403
        assert called == []


def test_no_configured_origin_fails_closed_and_public_get_remains_available():
    app, _, called = secure_app(None)
    with TestClient(app, base_url=ORIGIN) as client:
        client.get("/api/v1/me")
        assert client.post("/api/v1/change", json={}, headers=headers(client)).status_code == 403
        assert client.get("/api/v1/regions", headers={"Origin": "https://attacker.test"}).status_code == 200
        assert called == []


def test_redis_failure_cannot_bypass_csrf_validation():
    app, store, called = secure_app()
    with TestClient(app, base_url=ORIGIN) as client:
        client.get("/api/v1/me")

        async def fail(*args, **kwargs):
            raise StoreUnavailable

        store.load = fail
        response = client.post("/api/v1/change", json={}, headers=headers(client))
        assert response.status_code == 503 and response.json()["code"] == "SERVICE_UNAVAILABLE"
        assert called == []


def test_exact_json_byte_limit_and_oversized_rejection_before_handler():
    app, _, called = secure_app()
    with TestClient(app, base_url=ORIGIN) as client:
        client.get("/api/v1/me")
        supplied = headers(client) | {"Content-Type": "application/json"}
        body = json.dumps({"value": "a" * (65536 - 12)}, separators=(",", ":")).encode()
        assert len(body) == 65536
        assert client.post("/api/v1/change", content=body, headers=supplied).status_code == 200
        called.clear()
        response = client.post("/api/v1/change", content=body + b" ", headers=supplied)
        assert response.status_code == 413 and response.json()["code"] == "PAYLOAD_TOO_LARGE"
        assert called == []


def test_actual_length_mismatch_is_rejected_without_executing_handler():
    app, _, called = secure_app()
    with TestClient(app, base_url=ORIGIN) as client:
        client.get("/api/v1/me")
        supplied = headers(client) | {"Content-Length": "1", "Content-Type": "application/json"}
        assert client.post("/api/v1/change", content=b"{}", headers=supplied).status_code == 422
        assert called == []


def test_non_ascii_csrf_cookie_is_rejected_as_403_instead_of_500():
    app, _, called = secure_app()
    with TestClient(app, base_url=ORIGIN) as client:
        client.get("/api/v1/me")
        cookie = f"__Host-rc_session={client.cookies.get('__Host-rc_session')}; __Host-rc_csrf=".encode() + b"\xff"
        supplied = [(b"origin", ORIGIN.encode()), (b"x-csrf-token", client.cookies.get("__Host-rc_csrf").encode()), (b"cookie", cookie)]
        assert client.post("/api/v1/change", content=b"{}", headers=supplied).status_code == 403
        assert called == []


def test_multipart_upload_has_a_separate_bounded_envelope_allowance():
    app, _, called = secure_app()

    @app.post("/api/v1/journeys/{id}/transcriptions")
    async def upload(request: Request):
        called.append(True)
        return {"length": len(await request.body())}

    with TestClient(app, base_url=ORIGIN) as client:
        client.get("/api/v1/me")
        supplied = headers(client) | {"Content-Type": "multipart/form-data; boundary=test"}
        path = "/api/v1/journeys/11111111-1111-4111-8111-111111111111/transcriptions"
        assert client.post(path, content=b"x" * 65537, headers=supplied).status_code == 200
        called.clear()
        assert client.post(path, content=b"x" * (6 * 1024 * 1024 + 65537), headers=supplied).status_code == 413
        assert called == []


@pytest.mark.parametrize("extra", [
    [("Content-Length", "2"), ("Content-Length", "3")],
    [("Content-Length", "2"), ("Transfer-Encoding", "chunked")],
    [("Content-Length", "not-a-number")],
    [("Content-Encoding", "gzip")],
])
def test_ambiguous_lengths_and_compressed_inputs_are_rejected(extra):
    app, _, called = secure_app()
    with TestClient(app, base_url=ORIGIN) as client:
        client.get("/api/v1/me")
        assert client.post("/api/v1/change", content=b"{}", headers=list(headers(client).items()) + extra).status_code == 422
        assert called == []


def test_chunked_request_without_content_length_is_counted_by_actual_bytes():
    app, _, _ = secure_app()

    async def scenario():
        async def chunks():
            yield b"x" * 40000
            yield b"x" * 30000

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            response = await client.request("GET", "/api/v1/read-bytes", content=chunks())
            assert response.status_code == 413

    asyncio.run(scenario())


def test_cors_preflight_and_credentials_are_not_enabled_for_external_sites():
    app, _, _ = secure_app()
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.options("/api/v1/change", headers={"Origin": "https://attacker.test", "Access-Control-Request-Method": "POST"})
        assert not any(key.startswith("access-control-allow") for key in response.headers)


def test_untrusted_proxy_cannot_replace_client_ip():
    async def echo(scope, receive, send):
        from starlette.responses import JSONResponse
        await JSONResponse({"ip": scope["client"][0]})(scope, receive, send)

    async def scenario(peer, expected):
        wrapped = ProxyHeadersMiddleware(echo, trusted_hosts=["127.0.0.1"])
        transport = httpx.ASGITransport(app=wrapped, client=(peer, 1234))
        async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
            response = await client.get("/", headers={"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Proto": "https"})
            assert response.json()["ip"] == expected

    asyncio.run(scenario("10.0.0.7", "10.0.0.7"))
    asyncio.run(scenario("127.0.0.1", "203.0.113.9"))


def test_proxy_trust_has_no_wildcard_and_origin_is_canonical():
    assert Settings(_env_file=None).trusted_proxy_ips == []
    with pytest.raises(ValidationError):
        Settings(_env_file=None, trusted_proxy_ips=["*"])
    assert canonical_origin("https://EXAMPLE.org:443") == "https://example.org"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", public_origin="http://example.org")
