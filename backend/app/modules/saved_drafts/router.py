"""자기 지원서의 목록·상세·승인본 저장. 본문과 소유자는 서버가 고른다."""

from uuid import UUID
from fastapi import APIRouter, Query, Request
from starlette.responses import JSONResponse

from app.contracts.saved_drafts import DraftSaveRequest, DraftSaveResult, SavedDraft, SavedDraftList
from app.modules.requests.http import idempotency_key
from app.modules.sessions.http import require_session

router = APIRouter(tags=['회원 저장'])


async def session_for(request, *, activity=False):
    session = await require_session(request, user_activity=activity)
    await request.app.state.admission_service.check_http(request.client.host if request.client else '', session.subject_id)
    return session


@router.get('/drafts', response_model=SavedDraftList, operation_id='listSavedDrafts')
async def listing(request: Request, page: int = Query(default=1, ge=1, le=2**31-1), page_size: int = Query(default=20, ge=1, le=20)):
    result = await request.app.state.saved_draft_service.listing(await session_for(request), page, page_size)
    return JSONResponse(result.model_dump(mode='json'), headers={'Cache-Control': 'no-store'})


@router.get('/drafts/{document_id}', response_model=SavedDraft, operation_id='getSavedDraft')
async def get(document_id: UUID, request: Request):
    result = await request.app.state.saved_draft_service.get(await session_for(request), document_id)
    return JSONResponse(result.model_dump(mode='json'), headers={'Cache-Control': 'no-store'})


@router.post('/drafts', response_model=DraftSaveResult, status_code=201, operation_id='saveDraft')
async def save(request: Request, body: DraftSaveRequest):
    result = await request.app.state.saved_draft_service.save(await session_for(request, activity=True), idempotency_key(request), body)
    return JSONResponse(result.model_dump(mode='json'), status_code=201, headers={'Cache-Control': 'no-store'})
