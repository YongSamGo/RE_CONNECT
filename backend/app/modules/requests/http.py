"""업무 라우터가 세션·동의·소유권 검사를 마친 뒤 사용하는 헤더 경계."""

from starlette.requests import Request

from app.core.business_errors import AppError


def idempotency_key(request: Request) -> str:
    values = request.headers.getlist("idempotency-key")
    if len(values) != 1:
        raise AppError("VALIDATION_FAILED")
    return values[0]
