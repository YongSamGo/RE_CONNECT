"""회원 중요 요청의 서버 주체 검사. 쿠키에서 현재 세션을 다시 읽는다."""

from fastapi import Request

from app.modules.sessions.http import require_session


async def require_member(request: Request, *, reauth=False, operator=False):
    session = await require_session(request, user_activity=True)
    return await request.app.state.member_service.require(session, reauth=reauth, operator=operator)
