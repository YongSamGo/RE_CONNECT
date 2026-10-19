"""익명 /me bootstrap. 자격증명·주체 UUID·내부 수명 정보는 본문에 넣지 않는다."""

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.modules.sessions.http import cookie_names, read_cookie, write_csrf_cookie, write_session_cookie
from app.modules.sessions.service import csrf_token, valid_csrf_cookie

router = APIRouter()


@router.get("/me")
async def get_me(request: Request):
    service = request.app.state.session_service
    session_name, csrf_name = cookie_names(request)
    session = await service.resolve(read_cookie(request, session_name))
    issued = None
    if session is None:
        issued = await service.issue()
        session = issued.session
    # 계정 인증/저장 대기는 #73/#74, 동의는 #21에서 연결한다. 이 경로는 익명 상태만 발급한다.
    response = JSONResponse(
        {"authenticated": False, "user": None, "consents": [], "pending_save_intent": None},
        headers={"Cache-Control": "no-store"},
    )
    if issued is not None:
        write_session_cookie(request, response, issued)
    if not valid_csrf_cookie(session, read_cookie(request, csrf_name)):
        write_csrf_cookie(request, response, csrf_token(session), session)
    return response
