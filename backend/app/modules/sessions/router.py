"""익명 /me bootstrap. 자격증명·주체 UUID·내부 수명 정보는 본문에 넣지 않는다."""

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, Response

from app.modules.sessions.http import cookie_names, read_cookie, require_session, write_csrf_cookie, write_session_cookie
from app.modules.sessions.service import csrf_token, valid_csrf_cookie
from app.core.business_errors import AppError
from app.modules.consents.service import ConsentActor
from uuid import UUID

router = APIRouter()


@router.get("/me")
async def get_me(request: Request):
    service = request.app.state.session_service
    session_name, csrf_name = cookie_names(request)
    session = await service.resolve(read_cookie(request, session_name))
    await request.app.state.admission_service.check_http(request.client.host if request.client else '', session.subject_id if session else None)
    issued = None
    if session is None:
        issued = await service.issue()
        session = issued.session
    # 회원 결합/현재 DB 상태를 서버에서 읽는다. 저장 대기/동의 버전은 별도 모듈로 연결한다.
    try:
        view = await request.app.state.member_service.me(session)
    except AppError as error:
        if error.code != "SESSION_EXPIRED":
            raise
        issued = await request.app.state.member_service.logout(session)
        session = issued.session
        view = await request.app.state.member_service.me(session)
    actor = ConsentActor(session.subject_id, member_id=UUID(view['user']['id']) if view['authenticated'] else None,
                         session_digest=session.digest)
    states = await request.app.state.consent_service.current(actor)
    view['consents'] = [item.model_dump(mode='json') for item in states]
    if view['authenticated']:
        pending = await request.app.state.member_service.pending_save(session)
        view['pending_save_intent'] = pending.model_dump(mode='json') if pending else None
    response = JSONResponse(
        view,
        headers={"Cache-Control": "no-store"},
    )
    if issued is not None:
        write_session_cookie(request, response, issued)
    if not valid_csrf_cookie(session, read_cookie(request, csrf_name)):
        write_csrf_cookie(request, response, csrf_token(session), session)
    return response


@router.post("/auth/logout", status_code=204)
async def logout(request: Request):
    session = await require_session(request)
    issued = await request.app.state.member_service.logout(session)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    write_session_cookie(request, response, issued)
    write_csrf_cookie(request, response, csrf_token(issued.session), issued.session)
    return response
