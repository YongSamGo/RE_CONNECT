"""미승인 임시 지원서 생성. 모델 주체와 소유자는 서버 세션에서 정한다."""

from uuid import UUID
from fastapi import APIRouter, Request

from app.contracts.drafts import DraftCreate, JourneyDraft
from app.modules.admission.service import InferenceIdentity
from app.modules.requests.http import idempotency_key
from app.modules.sessions.http import require_session

router = APIRouter(tags=['체험'])


@router.post('/journeys/{journey_id}/drafts', response_model=JourneyDraft, status_code=201, operation_id='createJourneyDraft')
async def create_draft(journey_id: UUID, request: Request, body: DraftCreate):
    session = await require_session(request, user_activity=True)
    peer = request.client.host if request.client else ''
    await request.app.state.admission_service.check_http(peer, session.subject_id)
    return await request.app.state.draft_service.create(session, InferenceIdentity(session.subject_id, peer),
        journey_id, idempotency_key(request), body)
