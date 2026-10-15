"""요청 추적 ID (`X-Request-ID`).

모든 응답에 서버가 만든 `req_<32자 hex>`를 붙이고, 오류 본문의 `request_id`에도 같은 값을 넣는다.
클라이언트가 보낸 `X-Request-ID`는 받지 않는다. 임의 문자열이 로그·오류 응답으로 들어가
추적 기록을 위조하거나 로그를 오염시키지 않게 하기 위해서다.
"""

import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_STATE_KEY = "request_id"

_current_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def current_request_id() -> str | None:
    """지금 처리 중인 요청의 추적 ID. 로그 등 요청 객체가 없는 곳에서 쓴다."""
    return _current_request_id.get()


def get_request_id(request: Request) -> str:
    """요청의 추적 ID. 미들웨어 밖에서 만들어진 응답이라도 비어 있지 않게 새로 만든다."""
    request_id = request.scope.get("state", {}).get(_STATE_KEY)
    if request_id is None:
        request_id = new_request_id()
        request.scope.setdefault("state", {})[_STATE_KEY] = request_id
    return request_id


class RequestIdMiddleware:
    """요청마다 추적 ID를 만들고 응답 헤더에 붙인다.

    scope["state"]를 그대로 고쳐 두므로, 안쪽의 오류 처리(errors.py)도 같은 ID를 읽는다.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = new_request_id()
        scope.setdefault("state", {})[_STATE_KEY] = request_id
        token = _current_request_id.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _current_request_id.reset(token)
