"""HTTP 쿠키 경계. 개발 HTTP 예외는 서버 설정으로만 선택한다."""

import math

from fastapi import Request, Response

from app.core.business_errors import AppError
from app.modules.sessions.service import ABSOLUTE_MS, IssuedSession, Session


def cookie_names(request: Request) -> tuple[str, str]:
    if request.app.state.settings.app_env == "development":
        return "rc_session", "rc_csrf"
    return "__Host-rc_session", "__Host-rc_csrf"


def read_cookie(request: Request, name: str) -> str | None:
    values = []
    for header in request.headers.getlist("cookie"):
        for item in header.split(";"):
            key, separator, value = item.strip().partition("=")
            if separator and key == name:
                values.append(value)
    # 같은 이름의 여러 쿠키는 모호하게 해석하지 않는다. 임의 요청 헤더로 개발 모드를 선택하지 않는다.
    return values[0] if len(values) == 1 else None


def write_session_cookie(request: Request, response: Response, issued: IssuedSession) -> None:
    session_name, _ = cookie_names(request)
    remaining = max(0, issued.session.created_ms + ABSOLUTE_MS - issued.session.now_ms)
    response.set_cookie(
        session_name, issued.token, max_age=math.ceil(remaining / 1000), path="/",
        httponly=True, secure=request.app.state.settings.app_env != "development", samesite="lax",
    )


def write_csrf_cookie(request: Request, response: Response, token: str, session: Session) -> None:
    _, csrf_name = cookie_names(request)
    remaining = max(0, session.created_ms + ABSOLUTE_MS - session.now_ms)
    response.set_cookie(
        csrf_name, token, max_age=math.ceil(remaining / 1000), path="/",
        httponly=False, secure=request.app.state.settings.app_env != "development", samesite="strict",
    )


async def require_session(request: Request, *, user_activity: bool = False) -> Session:
    session_name, _ = cookie_names(request)
    session = await request.app.state.session_service.resolve(read_cookie(request, session_name), touch=user_activity)
    if session is None:
        raise AppError("NOT_FOUND")
    return session
