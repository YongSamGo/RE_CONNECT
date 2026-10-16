"""공통 오류 본문과 기본 처리기.

모든 오류는 `{code, message, request_id}`(422만 `fields` 추가)로 돌려준다 (docs/api/README.md §2.5).
원본 입력·예외 메시지·경로·추적 정보는 응답에 넣지 않는다.
여기서는 프레임워크가 내는 HTTP 오류·422·처리하지 못한 예외만 맞춘다. 업무 오류 코드와 로그 정리는 #26(W03-07)에서 더한다.
"""

import logging
import re
from collections.abc import Sequence
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_id import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)

FieldReason = Literal[
    "required",
    "invalid_type",
    "invalid_value",
    "too_long",
    "too_short",
    "out_of_range",
    "unknown_field",
    "required_with",
]

MAX_FIELD_ERRORS = 50
_MAX_PATH_LENGTH = 200
_LOCATIONS = frozenset({"body", "query", "path", "header", "cookie"})
# 경로 조각으로 되돌려 줄 수 있는 키. 정의하지 않은 필드와 dict 필드의 키는 키 이름 자체가 클라이언트 입력이므로
# 식별자 형식이 아니면 고정 표시로 바꿔 반사하지 않는다. 오류 종류로 가려내면 dict 키 같은 경우를 놓치므로
# 모든 키에 형식 검사를 건다.
_SAFE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
# 헤더는 스키마에 정의한 이름만 검증 대상이 되고(`Idempotency-Key` 등) 하이픈을 쓰므로 하이픈을 허용한다.
_SAFE_HEADER_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")
_UNSAFE_KEY = "<unknown>"

# Pydantic 오류 type → 계약의 reason. 목록에 없는 type은 invalid_value로 둔다.
_REASON_BY_PYDANTIC_TYPE: dict[str, FieldReason] = {
    "missing": "required",
    "extra_forbidden": "unknown_field",
    "string_too_long": "too_long",
    "too_long": "too_long",
    "string_too_short": "too_short",
    "too_short": "too_short",
    "greater_than": "out_of_range",
    "greater_than_equal": "out_of_range",
    "less_than": "out_of_range",
    "less_than_equal": "out_of_range",
    "multiple_of": "out_of_range",
    # app/contracts가 내는 사용자 정의 오류
    "required_with": "required_with",
}
_INVALID_TYPE_SUFFIXES = ("_type", "_parsing")

MESSAGES = {
    "UNAUTHENTICATED": "로그인이 필요합니다.",
    "FORBIDDEN": "이 작업을 할 권한이 없습니다.",
    "NOT_FOUND": "찾을 수 없거나 이용 시간이 지났습니다.",
    "PAYLOAD_TOO_LARGE": "보낸 내용이 너무 큽니다.",
    "RATE_LIMITED": "요청이 많습니다. 잠시 후 다시 시도해 주세요.",
    "VALIDATION_FAILED": "입력 내용을 확인해 주세요.",
    "INTERNAL_ERROR": "일시적인 문제가 생겼습니다. 잠시 뒤 다시 시도해 주세요.",
}


class FieldError(BaseModel):
    path: str
    reason: FieldReason


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    fields: list[FieldError] | None = None


def _error_json(
    request_id: str,
    status_code: int,
    code: str,
    fields: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorBody(code=code, message=MESSAGES[code], request_id=request_id, fields=fields)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        headers={**(headers or {}), REQUEST_ID_HEADER: request_id},
    )


def error_response(
    request: Request,
    status_code: int,
    code: str,
    fields: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return _error_json(get_request_id(request), status_code, code, fields, headers)


def _field_path(loc: Sequence[int | str], error_type: str) -> str:
    location = loc[0] if loc else "body"
    # 첫 요소(body·query·path·header·cookie)는 위치 구분이므로 경로에서 뺀다.
    parts = loc[1:] if loc and loc[0] in _LOCATIONS else loc
    # JSON 문법 오류의 loc 뒤쪽은 필드가 아니라 글자 위치다.
    if error_type == "json_invalid":
        parts = ()
    safe_key = _SAFE_HEADER_KEY if location == "header" else _SAFE_KEY
    path = ""
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            key = part if safe_key.fullmatch(part) else _UNSAFE_KEY
            path += f".{key}" if path else key
    # 본문 전체에 대한 오류(본문 없음·배열 본문 등)는 위치 이름으로 표시한다.
    if not path or path.startswith("["):
        path = f"{location}{path}" if location in _LOCATIONS else f"body{path}"
    return path[:_MAX_PATH_LENGTH]


def _field_reason(error_type: str) -> FieldReason:
    if error_type in _REASON_BY_PYDANTIC_TYPE:
        return _REASON_BY_PYDANTIC_TYPE[error_type]
    if error_type.endswith(_INVALID_TYPE_SUFFIXES):
        return "invalid_type"
    return "invalid_value"


def to_field_errors(errors: Sequence[Any]) -> list[FieldError]:
    """Pydantic 오류를 계약 형식으로 바꾼다. 입력값(`input`)과 원문 메시지(`msg`)는 버린다."""
    return [
        FieldError(
            path=_field_path(error.get("loc", ()), error.get("type", "")),
            reason=_field_reason(error.get("type", "")),
        )
        for error in errors[:MAX_FIELD_ERRORS]
    ]


# 프레임워크가 내는 4xx를 계약 코드로 옮긴다. 계약 코드가 있는 상태는 그대로 두고, 코드가 없는 400·415 등은
# 입력 오류로 보고 422로 답한다. 5xx만 INTERNAL_ERROR다.
_CODE_BY_STATUS = {
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    413: "PAYLOAD_TOO_LARGE",
    429: "RATE_LIMITED",
}
_BODY_FIELD_ERROR = [FieldError(path="body", reason="invalid_value")]


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    status_code = exc.status_code
    if status_code == 405:
        # 계약에 405 코드가 없다. 허용 메서드를 알려 주지 않고 없는 경로와 똑같이 404로 답한다.
        status_code = 404
    if status_code in _CODE_BY_STATUS:
        headers = None
        retry_after = (exc.headers or {}).get("Retry-After")
        if status_code == 429 and retry_after is not None:
            headers = {"Retry-After": retry_after}
        return error_response(request, status_code, _CODE_BY_STATUS[status_code], headers=headers)
    if 400 <= status_code < 500:
        return error_response(request, 422, "VALIDATION_FAILED", fields=_BODY_FIELD_ERROR)
    logger.warning("처리 코드가 없는 HTTP 오류: status=%s", status_code)
    return error_response(request, 500, "INTERNAL_ERROR")


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(request, 422, "VALIDATION_FAILED", fields=to_field_errors(exc.errors()))


class UnhandledErrorMiddleware:
    """처리하지 못한 예외를 500 계약 본문으로 바꾸고 예외를 다시 던지지 않는다.

    FastAPI의 `Exception` 처리기는 Starlette `ServerErrorMiddleware`에서 돌고, 응답을 보낸 뒤
    서버가 기록하도록 예외를 다시 던진다. 그러면 uvicorn이 예외 메시지·traceback 전체를 로그에 남겨
    접속 문자열·사용자 입력이 새어 나갈 수 있다. 그래서 여기서 잡아 예외 종류와 request_id만 남긴다.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_tracking_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking_start)
        except Exception as exc:
            request_id = get_request_id(Request(scope))
            # 예외 메시지에 입력·경로가 섞일 수 있어 종류만 남긴다. 추적 정보를 남기는 방식은 #26에서 정한다.
            logger.error("처리하지 못한 예외: type=%s request_id=%s", type(exc).__name__, request_id)
            if response_started:
                # 이미 보낸 응답은 바꿀 수 없다. 서버가 연결을 닫게 두고 원문은 넘기지 않는다.
                return
            await _error_json(request_id, 500, "INTERNAL_ERROR")(scope, receive, send)


def register_error_handlers(app: FastAPI) -> None:
    """HTTP 오류·422 처리기를 등록한다. 처리하지 못한 예외는 UnhandledErrorMiddleware가 맡는다."""
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
