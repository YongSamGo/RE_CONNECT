"""동의 수락 API. 회원 인증 연결 전에는 익명 AI 동의만 허용한다."""

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.core.errors import FieldError, error_response
from app.modules.consents.models import ConsentCreate
from app.modules.consents.service import ConsentActor, ConsentVersionError
from app.modules.sessions.http import require_session

router = APIRouter()


@router.post("/consents")
async def create_consent(request: Request, body: ConsentCreate):
    session = await require_session(request, user_activity=True)
    account = await request.app.state.member_service.require(session) if session.user_id is not None else None
    actor = ConsentActor(session.subject_id, member_id=account.id if account else None, session_digest=session.digest,
                         member_generation=account.generation if account else None)
    try:
        state, created = await request.app.state.consent_service.grant(actor, body)
    except ConsentVersionError:
        return error_response(request, 422, "VALIDATION_FAILED", fields=[FieldError(path="notice_version", reason="invalid_value")])
    if account is not None:
        await request.app.state.member_service.require(session)
    return JSONResponse(state.model_dump(mode="json"), status_code=201 if created else 200,
                        headers={"Cache-Control": "no-store"})
