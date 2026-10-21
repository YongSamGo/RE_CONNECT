"""세션·Origin·CSRF·한도·멱등 키를 통과한 승인 참조 발급 API."""

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.contracts.save_intents import SaveIntentCreate
from app.core.errors import FieldError, error_response
from app.modules.requests.http import idempotency_key
from app.modules.sessions.http import require_session

router = APIRouter()


@router.post('/auth/save-intents', status_code=201, operation_id='createSaveIntent')
async def create_save_intent(request: Request, body: SaveIntentCreate):
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(request.client.host if request.client else '', session.subject_id)
    if body.profile is None:
        return error_response(request, 422, 'VALIDATION_FAILED', fields=[
            FieldError(path='profile', reason='required_with' if body.draft is not None else 'required')])
    result = await request.app.state.save_intent_service.create(session, idempotency_key(request), body)
    return JSONResponse(result.model_dump(mode='json'), status_code=201, headers={'Cache-Control': 'no-store'})
