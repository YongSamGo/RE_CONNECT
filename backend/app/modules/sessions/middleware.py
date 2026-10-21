"""API 변경 요청 CSRF·Origin, 입력 크기와 사적 응답 캐시 경계 (W03-03)."""

import hmac

from starlette.requests import Request
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.business_errors import AppError
from app.core.config import canonical_origin
from app.core.errors import error_response, FieldError
from app.modules.sessions.http import cookie_names, read_cookie
from app.modules.sessions.service import valid_csrf_cookie

JSON_LIMIT = 64 * 1024
AUDIO_REQUEST_LIMIT = 6 * 1024 * 1024 + JSON_LIMIT


class RequestSecurityMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or not (scope["path"] == "/api/v1" or scope["path"].startswith("/api/v1/")):
            await self.app(scope, receive, send)
            return
        request = Request(scope)

        async def reject(code, status):
            fields = [FieldError(path="body", reason="invalid_value")] if status == 422 else None
            await error_response(request, status, code, fields=fields)(scope, receive, send)

        # 컨텐츠 길이/형식 헤더의 중복과 압축 본문은 모호하게 해석하지 않는다.
        lengths = request.headers.getlist("content-length")
        types = request.headers.getlist("content-type")
        encodings = request.headers.getlist("content-encoding")
        if (
            len(lengths) > 1 or len(types) > 1 or len(encodings) > 1
            or lengths and request.headers.get("transfer-encoding")
            or lengths and (not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 10)
            or encodings and encodings[0].lower() != "identity"
        ):
            await reject("VALIDATION_FAILED", 422)
            return
        parts = scope["path"].split("/")
        audio_upload = len(parts) == 6 and parts[3] == "journeys" and parts[5] == "transcriptions"
        content_type = (types[0].split(";", 1)[0].strip().lower() if types else "")
        limit = AUDIO_REQUEST_LIMIT if audio_upload and content_type == "multipart/form-data" else JSON_LIMIT
        declared = int(lengths[0]) if lengths else None
        if declared is not None and declared > limit:
            await reject("PAYLOAD_TOO_LARGE", 413)
            return

        registered = any(route.matches(scope)[0] == Match.FULL for route in request.app.router.routes)
        if scope["method"] != "GET" and registered:
            origins = request.headers.getlist("origin")
            expected = request.app.state.settings.public_origin
            try:
                actual = canonical_origin(origins[0]) if len(origins) == 1 else None
            except ValueError:
                actual = None
            if expected is None or actual is None or actual != expected:
                await reject("CSRF_FAILED", 403)
                return
            session_name, csrf_name = cookie_names(request)
            headers = request.headers.getlist("x-csrf-token")
            cookie = read_cookie(request, csrf_name)
            if len(headers) != 1 or cookie is None or len(headers[0]) > 128 or not headers[0].isascii() or not cookie.isascii() or not hmac.compare_digest(headers[0], cookie):
                await reject("CSRF_FAILED", 403)
                return
            try:
                session = await request.app.state.session_service.resolve(read_cookie(request, session_name))
            except AppError as error:
                await reject(error.code, 503)
                return
            if session is None or not valid_csrf_cookie(session, cookie):
                await reject("CSRF_FAILED", 403)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                await reject("PAYLOAD_TOO_LARGE", 413)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        if declared is not None and declared != len(body):
            await reject("VALIDATION_FAILED", 422)
            return

        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        # 공개 목록·공고 상세·공식 준비 안내 GET만 기존 공개 캐시 정책을 유지한다.
        opportunity_read = (
            scope["path"] == "/api/v1/opportunities"
            or len(parts) == 5 and parts[3] == "opportunities"
            or len(parts) == 6 and parts[3] == "opportunities" and parts[5] == "preparation"
        )
        public_get = scope["method"] == "GET" and (scope["path"] == "/api/v1/regions" or opportunity_read)

        async def secure_response(message: Message):
            if message["type"] == "http.response.start" and not public_get:
                from starlette.datastructures import MutableHeaders
                MutableHeaders(scope=message)["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, replay, secure_response)
