"""운영자 MFA 확인. 성공하면 세션·CSRF를 새로 발급한다(권한 상승 시 세션 교체)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.core.request_id import get_request_id
from app.modules.operators.models import MfaStatus, MfaVerify
from app.modules.sessions.http import require_session, write_csrf_cookie, write_session_cookie
from app.modules.sessions.service import csrf_token

router = APIRouter()


@router.post("/admin/mfa/verify", operation_id="verifyMfa")
async def verify_mfa(request: Request, body: MfaVerify):
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    issued, until_ms = await request.app.state.operator_mfa_service.verify(session, body.otp, get_request_id(request))
    status = MfaStatus(mfa_verified=True, expires_at=datetime.fromtimestamp(until_ms / 1000, UTC))
    response = JSONResponse({"mfa_verified": True, "expires_at": status.expires_at.isoformat().replace("+00:00", "Z")},
                            headers={"Cache-Control": "no-store"})
    write_session_cookie(request, response, issued)
    write_csrf_cookie(request, response, csrf_token(issued.session), issued.session)
    return response
