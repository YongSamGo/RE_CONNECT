"""익명 /me bootstrap. 자격증명·주체 UUID·내부 수명 정보는 본문에 넣지 않는다."""

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.modules.sessions.http import cookie_names, read_cookie, write_csrf_cookie, write_session_cookie
from app.modules.sessions.service import csrf_token, valid_csrf_cookie
from app.modules.consents.service import ConsentActor

router = APIRouter()


@router.get("/me")
async def get_me(request: Request):
    service = request.app.state.session_service
    session_name, csrf_name = cookie_names(request)
    session = await service.resolve(read_cookie(request, session_name))
    # 새 주체 발급 전 IP 한도부터 확인한다. peer는 신뢰 프록시 처리가 끝난 ASGI 주소다.
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id if session else None)
    issued = None
    if session is None:
        issued = await service.issue()
        session = issued.session
    consents = await request.app.state.consent_service.current(ConsentActor(session.subject_id, session_digest=session.digest))
    # 계정 인증/저장 대기는 #73/#74에서 연결한다. 이 경로는 익명 상태만 발급한다.
    response = JSONResponse(
        {"authenticated": False, "user": None, "consents": [item.model_dump(mode="json") for item in consents], "pending_save_intent": None},
        headers={"Cache-Control": "no-store"},
    )
    if issued is not None:
        write_session_cookie(request, response, issued)
    if not valid_csrf_cookie(session, read_cookie(request, csrf_name)):
        write_csrf_cookie(request, response, csrf_token(session), session)
    return response
