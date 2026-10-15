"""공통 오류 본문과 기본 처리기.

모든 오류는 `{code, message, request_id}`(422만 `fields` 추가)로 돌려준다 (docs/api/README.md §2.5).
원본 입력·예외 메시지·경로·추적 정보는 응답에 넣지 않는다.
여기서는 프레임워크가 내는 404·405·422·500만 맞춘다. 업무 오류 코드와 로그 정리는 #26(W03-07)에서 더한다.
"""

import logging
from collections.abc import Sequence
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

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
}
_INVALID_TYPE_SUFFIXES = ("_type", "_parsing")

MESSAGES = {
    "NOT_FOUND": "찾을 수 없거나 이용 시간이 지났습니다.",
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


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    fields: list[FieldError] | None = None,
) -> JSONResponse:
    request_id = get_request_id(request)
    body = ErrorBody(code=code, message=message, request_id=request_id, fields=fields)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        # RequestIdMiddleware 바깥(500 처리)에서도 같은 ID가 헤더에 실리게 직접 붙인다.
        headers={REQUEST_ID_HEADER: request_id},
    )


def _field_path(loc: Sequence[int | str]) -> str:
    # 첫 요소(body·query·path·header·cookie)는 위치 구분이므로 경로에서 뺀다.
    parts = loc[1:] if loc and loc[0] in {"body", "query", "path", "header", "cookie"} else loc
    path = ""
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
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
        FieldError(path=_field_path(error.get("loc", ())), reason=_field_reason(error.get("type", "")))
        for error in errors[:MAX_FIELD_ERRORS]
    ]


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code in (404, 405):
        # 계약에 405 코드가 없다. 허용 메서드를 알려 주지 않고 없는 경로와 똑같이 404로 답한다.
        return error_response(request, 404, "NOT_FOUND", MESSAGES["NOT_FOUND"])
    # 그 밖의 HTTPException은 아직 쓰지 않는다. 업무 오류는 #26에서 전용 예외로 처리한다.
    logger.warning("처리 코드가 없는 HTTP 오류: status=%s", exc.status_code)
    return error_response(request, 500, "INTERNAL_ERROR", MESSAGES["INTERNAL_ERROR"])


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        request,
        422,
        "VALIDATION_FAILED",
        MESSAGES["VALIDATION_FAILED"],
        fields=to_field_errors(exc.errors()),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # 예외 메시지에 입력·경로가 섞일 수 있어 종류만 남긴다. 추적 정보를 남기는 방식은 #26에서 정한다.
    logger.error("처리하지 못한 예외: type=%s request_id=%s", type(exc).__name__, get_request_id(request))
    return error_response(request, 500, "INTERNAL_ERROR", MESSAGES["INTERNAL_ERROR"])


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
