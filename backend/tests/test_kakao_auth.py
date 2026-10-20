"""실제 카카오 계정/코드/토큰 없이 HTTPS 계약·신원 대조·로그인 CSRF를 시험한다."""

import asyncio
import base64
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import httpx
from pydantic import SecretStr
import pytest
from starlette.datastructures import QueryParams

from app.adapters.auth import OAuthFailure
from app.adapters.kakao import KakaoAdapter
from app.modules.auth.service import Completion, OAuthService, UnavailableCompletionHandler
from tests.test_sessions import app_and_store


class FakeFlows:
    """서비스/HTTP 단위 시험용. Redis 원자성/수명 검증에 쓰지 않는다."""
    def __init__(self):self.records = {}
    async def create(self, session, digest, flow):
        self.records[(session, digest)] = flow
        return True
    async def consume(self, session, digest):return self.records.pop((session, digest), None)


class FakeCompletion:
    def __init__(self):self.calls = []
    async def eligible(self, session, purpose):return None
    async def complete(self, session, identity, purpose):
        self.calls.append((session.subject_id, identity.subject, purpose))
        return Completion("success")


def adapter(handler):
    return KakaoAdapter(SecretStr("fixture-key"), SecretStr("fixture-client-secret"), 123,
        "https://service.example/api/v1/auth/kakao/callback", transport=httpx.MockTransport(handler))


def responses(request, *, overrides=None):
    if request.url.path == "/oauth/token":
        value = {"access_token": "fixture-access", "token_type": "bearer", "expires_in": 60}
    elif request.url.path == "/v1/user/access_token_info":
        value = {"id": 456, "app_id": 123, "expires_in": 59}
    else:value = {"id": 456}
    return httpx.Response(200, json={**value, **(overrides or {})})


def test_three_fixed_https_calls_minimal_properties_and_matching_identity(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    requests = []
    def handle(request):
        requests.append(request)
        return responses(request)
    kakao = adapter(handle)
    assert asyncio.run(kakao.exchange("fixture-code", "v" * 43)) == "456"
    assert [(r.method, r.url.host, r.url.path) for r in requests] == [
        ("POST", "kauth.kakao.com", "/oauth/token"), ("GET", "kapi.kakao.com", "/v1/user/access_token_info"),
        ("POST", "kapi.kakao.com", "/v2/user/me")]
    form = parse_qs(requests[0].content.decode())
    assert form["code"] == ["fixture-code"] and form["code_verifier"] == ["v" * 43]
    assert form["client_secret"] == ["fixture-client-secret"]
    assert all("fixture-code" not in str(r.url) and "fixture-access" not in str(r.url) for r in requests)
    assert parse_qs(requests[-1].content.decode()) == {"property_keys": ["[]"]}
    assert requests[1].headers["authorization"] == "Bearer fixture-access"


@pytest.mark.parametrize("path,changes", [
    ("/oauth/token", {"token_type": "other"}), ("/oauth/token", {"expires_in": True}),
    ("/oauth/token", {"access_token": "x\r\nheader"}),
    ("/v1/user/access_token_info", {"app_id": 124}), ("/v1/user/access_token_info", {"app_id": True}),
    ("/v1/user/access_token_info", {"id": True}), ("/v1/user/access_token_info", {"id": -1}),
    ("/v1/user/access_token_info", {"expires_in": 0}), ("/v2/user/me", {"id": 457}),
    ("/v2/user/me", {"id": "456"}),
])
def test_token_wrong_app_identity_mismatch_and_invalid_types_fail_closed(path, changes):
    requests = []
    def handle(request):
        requests.append(request)
        return responses(request, overrides=changes if request.url.path == path else {})
    with pytest.raises(OAuthFailure) as failure:asyncio.run(adapter(handle).exchange("fixture-code", "v" * 43))
    assert "fixture" not in str(failure.value)
    assert len(requests) <= {"/oauth/token": 1, "/v1/user/access_token_info": 2, "/v2/user/me": 3}[path]


@pytest.mark.parametrize("kind", ["redirect", "oversize", "gzip", "html", "bad_json", "duplicate", "nan", "timeout"])
def test_provider_limits_and_errors_do_not_follow_or_echo(kind):
    requests = []
    def handle(request):
        requests.append(request)
        if kind == "timeout":raise httpx.ReadTimeout("fixture provider data")
        if kind == "redirect":return httpx.Response(302, headers={"location": "https://evil.example"})
        headers = {"content-type": "application/json"}
        if kind == "oversize":return httpx.Response(200, content=b" " * 65537, headers=headers)
        if kind == "gzip":return httpx.Response(200, headers={**headers, "content-encoding": "gzip"}, content=b"bad")
        if kind == "html":return httpx.Response(200, headers={"content-type": "text/html"}, content=b"fixture")
        if kind == "duplicate":return httpx.Response(200, headers=headers, content=b'{"access_token":"one","access_token":"two"}')
        if kind == "nan":return httpx.Response(200, headers=headers, content=b'{"extra":NaN}')
        return httpx.Response(200, headers=headers, content=b"fixture invalid")
    with pytest.raises(OAuthFailure):asyncio.run(adapter(handle).exchange("fixture-code", "v" * 43))
    assert len(requests) == 1


def configured_app():
    app, store, _ = app_and_store()
    flows, completion, requests = FakeFlows(), FakeCompletion(), []
    def handle(request):
        requests.append(request)
        return responses(request)
    app.state.oauth_service = OAuthService(flows, adapter(handle), completion)
    return app, store, flows, completion, requests


def begin(client, purpose="login"):
    response = client.get("/api/v1/auth/kakao/start", params={"purpose": purpose}, follow_redirects=False)
    assert response.status_code == 302
    return parse_qs(urlsplit(response.headers["location"]).query)


def test_http_start_issues_secure_cookie_pkce_and_only_fixed_parameters():
    app, _, flows, _, _ = configured_app()
    with TestClient(app, base_url="https://testserver") as client:
        params = begin(client)
        assert params["code_challenge_method"] == ["S256"] and "code_verifier" not in params
        flow = next(iter(flows.records.values()))
        expected = base64.urlsafe_b64encode(hashlib.sha256(flow.verifier.encode()).digest()).decode().rstrip("=")
        assert params["code_challenge"] == [expected] and flow.verifier not in repr(flow)
        assert client.cookies.get("__Host-rc_session")
        assert begin(client, "reauth")["prompt"] == ["login"]
        assert client.get("/api/v1/auth/kakao/start?purpose=login&return_to=https://evil.example", follow_redirects=False).status_code == 422
        assert client.get("/api/v1/auth/kakao/start?purpose=login&purpose=save", follow_redirects=False).status_code == 422
        assert client.get("/api/v1/auth/kakao/start?purpose=admin", follow_redirects=False).status_code == 422


def test_http_bound_state_one_use_safe_redirect_and_no_credentials(caplog):
    app, _, _, completion, requests = configured_app()
    with TestClient(app, base_url="https://testserver") as a, TestClient(app, base_url="https://testserver") as b:
        state = begin(a)["state"][0]
        begin(b)
        url = "/api/v1/auth/kakao/callback?" + "state=" + state + "&code=fixture-code"
        failed = b.get(url, follow_redirects=False)
        assert failed.headers["location"] == "/auth/result?purpose=login&status=failed" and not requests
        success = a.get(url, follow_redirects=False)
        assert success.headers["location"] == "/auth/result?purpose=login&status=success"
        assert len(requests) == 3 and len(completion.calls) == 1
        assert success.headers["cache-control"] == "no-store" and success.headers["referrer-policy"] == "no-referrer"
        a.get(url, follow_redirects=False)
        assert len(requests) == 3
        assert all(v not in success.text + success.headers["location"] for v in (state, "fixture-code", "fixture-access", "456"))
    # HTTP client debug records may contain a received query, but production formatter must drop all message fields.
    from app.core.safe_logging import SafeJsonFormatter
    formatted = "".join(SafeJsonFormatter().format(record) for record in caplog.records)
    assert state not in formatted and "fixture-code" not in formatted and "fixture-access" not in formatted


@pytest.mark.parametrize("suffix,status", [("&error=access_denied", "cancelled"), ("&error=other&error_description=fixture", "failed"),
    ("&code=one&code=two", "failed"), ("&code=one&error=access_denied", "failed"), ("&return_to=https://evil.example", "failed")])
def test_bad_or_cancelled_callback_consumes_state_without_exchange(suffix, status):
    app, _, _, _, requests = configured_app()
    with TestClient(app, base_url="https://testserver") as client:
        state = begin(client, "save")["state"][0]
        response = client.get("/api/v1/auth/kakao/callback?state=" + state + suffix, follow_redirects=False)
        assert response.headers["location"] == f"/auth/result?purpose=save&status={status}" and not requests
        client.get("/api/v1/auth/kakao/callback?state=" + state + "&code=fixture", follow_redirects=False)
        assert not requests


def test_default_completion_does_not_fabricate_account_or_success():
    app, _, flows, _, requests = configured_app()
    app.state.oauth_service.completion = UnavailableCompletionHandler()
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/api/v1/auth/kakao/start?purpose=save", follow_redirects=False).headers["location"].endswith("purpose=save&status=expired")
        assert client.get("/api/v1/auth/kakao/start?purpose=reauth", follow_redirects=False).headers["location"].endswith("purpose=reauth&status=failed")
        state = begin(client)["state"][0]
        response = client.get("/api/v1/auth/kakao/callback?state=" + state + "&code=fixture", follow_redirects=False)
        assert response.headers["location"].endswith("status=failed") and len(requests) == 3
        assert client.get("/api/v1/me").json()["authenticated"] is False


def test_nonconfigured_provider_and_missing_session_do_not_redirect_external_or_exchange():
    app, _, _, _, requests = configured_app()
    app.state.oauth_service.adapter = None
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/v1/auth/kakao/start?purpose=login", follow_redirects=False)
        assert response.status_code == 503 and "location" not in response.headers
        assert client.get("/api/v1/auth/kakao/callback?code=fixture&state=" + "a" * 43, follow_redirects=False).headers["location"].endswith("status=failed")
        assert not requests
