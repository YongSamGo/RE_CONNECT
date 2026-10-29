"""회원 중요 요청의 서버 주체 검사. 쿠키에서 현재 세션을 다시 읽는다."""

from fastapi import Request

from app.modules.sessions.http import require_session


async def require_member(request: Request, *, reauth=False, operator=False):
    session = await require_session(request, user_activity=True)
    return await request.app.state.member_service.require(session, reauth=reauth, operator=operator)


async def require_operator(request: Request):
    """`/admin/*` 공통 검사: 세션 → 요청 제한 → 운영자 역할·MFA. 화면 숨김에 기대지 않고 매 요청 다시 본다."""
    session = await require_session(request, user_activity=True, validate_member=False)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    return await request.app.state.member_service.require(session, operator=True)
