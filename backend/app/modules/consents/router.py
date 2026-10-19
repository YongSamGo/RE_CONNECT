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
    # #73의 회원 인증 전까지 헤더/본문/쿼리의 회원 ID를 신뢰하지 않는다.
    actor = ConsentActor(session.subject_id, session_digest=session.digest)
    try:
        state, created = await request.app.state.consent_service.grant(actor, body)
    except ConsentVersionError:
        return error_response(request, 422, "VALIDATION_FAILED", fields=[FieldError(path="notice_version", reason="invalid_value")])
    return JSONResponse(state.model_dump(mode="json"), status_code=201 if created else 200,
                        headers={"Cache-Control": "no-store"})
