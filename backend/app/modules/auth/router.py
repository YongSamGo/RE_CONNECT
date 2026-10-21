"""브라우저 로그인 왕복. callback은 민감 쿼리를 결과 주소/본문/로그로 복사하지 않는다."""

from typing import Literal

from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse

from app.core.business_errors import AppError
from app.modules.auth.service import Completion, result_location
from app.modules.sessions.http import cookie_names, read_cookie, write_csrf_cookie, write_session_cookie
from app.modules.sessions.service import csrf_token

router = APIRouter()


def redirect(location):
    return RedirectResponse(location, status_code=302, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/auth/kakao/start")
async def start(request: Request, purpose: Literal["login", "save", "reauth"]):
    if set(request.query_params) != {"purpose"} or len(request.query_params.getlist("purpose")) != 1:
        raise AppError("VALIDATION_FAILED")
    session_name, _ = cookie_names(request)
    sessions = request.app.state.session_service
    session = await sessions.resolve(read_cookie(request, session_name))
    issued = None
    if session is None:
        issued = await sessions.issue()
        session = issued.session
    location = await request.app.state.oauth_service.start(session, purpose)
    response = redirect(location)
    if issued is not None:
        write_session_cookie(request, response, issued)
        write_csrf_cookie(request, response, csrf_token(session), session)
    return response


@router.get("/auth/kakao/callback")
async def callback(request: Request):
    purpose, result = "login", Completion("failed")
    try:
        if len(request.scope.get("query_string", b"")) <= 4096:
            session_name, _ = cookie_names(request)
            session = await request.app.state.session_service.resolve(read_cookie(request, session_name))
            purpose, result = await request.app.state.oauth_service.callback(session, request.query_params)
    except AppError:
        pass  # 세션/Redis 장애도 허용한 고정 실패 주소로만 전달한다.
    response = redirect(result_location(purpose, result.status))
    if result.issued is not None:
        write_session_cookie(request, response, result.issued)
        write_csrf_cookie(request, response, csrf_token(result.issued.session), result.issued.session)
    return response
