"""고정 카카오 HTTPS 엔드포인트의 코드 교환/앱·신원 대조. 토큰은 메모리에서만 사용한다."""

import asyncio
import json
import re
from urllib.parse import urlencode

import httpx

from app.adapters.auth import OAuthFailure

KakaoUnavailable = OAuthFailure


class KakaoAdapter:
    def __init__(self, rest_key, client_secret, app_id, redirect_uri, *, transport=None):
        self._rest_key, self._client_secret = rest_key, client_secret
        self._app_id, self._redirect_uri, self._transport = app_id, redirect_uri, transport

    def authorization_url(self, state, challenge, purpose):
        values = {"response_type": "code", "client_id": self._rest_key.get_secret_value(),
                  "redirect_uri": self._redirect_uri, "state": state,
                  "code_challenge": challenge, "code_challenge_method": "S256"}
        if purpose == "reauth":
            values["prompt"] = "login"
        return "https://kauth.kakao.com/oauth/authorize?" + urlencode(values)

    @staticmethod
    async def _json(client, method, url, **kwargs):
        async with client.stream(method, url, **kwargs) as response:
            if (response.status_code != 200 or response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json"
                    or response.headers.get("content-encoding", "identity").lower() != "identity"):
                raise KakaoUnavailable
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise KakaoUnavailable
        def pairs(values):
            result = {}
            for key, value in values:
                if key in result:
                    raise KakaoUnavailable
                result[key] = value
            return result
        def constant(_value):
            raise KakaoUnavailable
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        if not isinstance(result, dict):
            raise KakaoUnavailable
        return result

    async def exchange(self, code, verifier):
        # 인가 코드와 시크릿은 POST 본문, 토큰은 Authorization 헤더에만 전달한다.
        # HTTP 라이브러리 로그에 코드가 든 URL을 만들지 않는다.
        try:
            if (not isinstance(code, str) or not 1 <= len(code) <= 512 or not code.isascii() or not code.isprintable()
                    or any(char.isspace() for char in code) or re.fullmatch(r"[A-Za-z0-9_-]{43}", verifier) is None):
                raise KakaoUnavailable
            async with asyncio.timeout(15):
                async with httpx.AsyncClient(transport=self._transport, trust_env=False, follow_redirects=False,
                        timeout=5, headers={"Accept": "application/json", "Accept-Encoding": "identity"}) as client:
                    token = await self._json(client, "POST", "https://kauth.kakao.com/oauth/token", data={
                        "grant_type": "authorization_code", "client_id": self._rest_key.get_secret_value(),
                        "client_secret": self._client_secret.get_secret_value(), "redirect_uri": self._redirect_uri,
                        "code": code, "code_verifier": verifier})
                    access = token.get("access_token")
                    if (token.get("token_type") != "bearer" or type(token.get("expires_in")) is not int or token["expires_in"] <= 0
                            or not isinstance(access, str) or len(access) > 4096 or re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", access) is None):
                        raise KakaoUnavailable
                    headers = {"Authorization": "Bearer " + access}
                    info = await self._json(client, "GET", "https://kapi.kakao.com/v1/user/access_token_info", headers=headers)
                    if (type(info.get("app_id")) is not int or info["app_id"] != self._app_id
                            or type(info.get("expires_in")) is not int or info["expires_in"] <= 0):
                        raise KakaoUnavailable
                    subject = info.get("id")
                    if type(subject) is not int or not 0 < subject <= 2**63 - 1:
                        raise KakaoUnavailable
                    # 프로필·이메일 등 추가 동의/정보를 요청하지 않는다. id만 사용한다.
                    user = await self._json(client, "POST", "https://kapi.kakao.com/v2/user/me", headers=headers,
                                            data={"property_keys": "[]"})
                    if type(user.get("id")) is not int or user["id"] != subject:
                        raise KakaoUnavailable
                    return str(subject)
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, RecursionError):
            raise KakaoUnavailable from None
