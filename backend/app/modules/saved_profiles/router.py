"""자기 프로필만 조회/저장한다. 공개 요청의 회원 ID·본문을 받지 않는다."""

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.contracts.saved_profiles import ProfileSaveRequest, ProfileSaveResult, SavedProfileResponse
from app.modules.requests.http import idempotency_key
from app.modules.sessions.http import require_session

router = APIRouter(tags=['회원 저장'])


async def member_session(request, *, user_activity=False):
    session = await require_session(request, user_activity=user_activity)
    await request.app.state.admission_service.check_http(request.client.host if request.client else '', session.subject_id)
    return session


@router.get('/profiles/me', response_model=SavedProfileResponse, operation_id='getSavedProfile')
async def get_profile(request: Request):
    result = await request.app.state.saved_profile_service.get(await member_session(request))
    return JSONResponse(result.model_dump(mode='json'), headers={'Cache-Control': 'no-store'})


@router.post('/profiles/me/versions', response_model=ProfileSaveResult,
             responses={201: {'model': ProfileSaveResult, 'description': '새 불변 버전'}}, operation_id='saveProfileVersion')
async def save_profile(request: Request, body: ProfileSaveRequest):
    result = await request.app.state.saved_profile_service.save(await member_session(request, user_activity=True), idempotency_key(request), body)
    return JSONResponse(result.model_dump(mode='json'), status_code=201 if result.created else 200, headers={'Cache-Control': 'no-store'})
