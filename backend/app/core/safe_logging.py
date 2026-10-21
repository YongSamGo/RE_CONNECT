"""허용한 메타데이터만 직렬화한다. 메시지·인자·예외·URL을 정규식으로 가리지 않는다."""

import json
import logging
import re
from datetime import UTC, datetime
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_id import current_request_id

_REQUEST_ID = re.compile(r"req_[0-9a-f]{32}")
_EVENTS = frozenset({"request_complete", "request_interrupted"})
_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
logger = logging.getLogger(__name__)


class SafeJsonFormatter(logging.Formatter):
    """외부 라이브러리의 로그도 고정 이벤트와 서버 메타데이터만 남긴다.

    getMessage/formatException을 호출하지 않아 객체의 문자열 변환으로 원문을 노출하지 않는다.
    로그 이름·소스 경로·스택·임의 extra 필드도 직렬화하지 않는다.
    """

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", None)
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": logging.getLevelName(record.levelno) if record.levelno in (10, 20, 30, 40, 50) else "INFO",
            "event": event if isinstance(event, str) and event in _EVENTS else "runtime_event",
        }
        request_id = current_request_id()
        if isinstance(request_id, str) and _REQUEST_ID.fullmatch(request_id):
            entry["request_id"] = request_id
        for field, low, high in (("status", 100, 599), ("duration_ms", 0, 86_400_000)):
            value = getattr(record, field, None)
            if type(value) is int and low <= value <= high:
                entry[field] = value
        method = getattr(record, "method", None)
        if isinstance(method, str) and method in _METHODS:
            entry["method"] = method
        return json.dumps(entry, ensure_ascii=True, separators=(",", ":"))


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {"safe": {"()": "app.core.safe_logging.SafeJsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "safe", "stream": "ext://sys.stdout"}},
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "app": {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn": {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn.error": {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn.access": {"level": "CRITICAL", "handlers": [], "propagate": False},
        "httpx": {"level": "WARNING", "handlers": [], "propagate": True},
        "httpcore": {"level": "WARNING", "handlers": [], "propagate": True},
    },
}


class RequestLogMiddleware:
    """URL·쿼리·헤더·본문·IP를 읽지 않고 요청 완료를 기록한다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = perf_counter()
        status = None
        complete = False

        async def track(message: Message) -> None:
            nonlocal status, complete
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                complete = True

        try:
            await self.app(scope, receive, track)
        finally:
            logger.info("request", extra={
                "event": "request_complete" if complete else "request_interrupted",
                "status": status,
                "duration_ms": int((perf_counter() - start) * 1000),
                "method": scope.get("method"),
            })
