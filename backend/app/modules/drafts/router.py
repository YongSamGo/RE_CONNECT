"""미승인 임시 지원서 생성. 모델 주체와 소유자는 서버 세션에서 정한다."""

from uuid import UUID
from fastapi import APIRouter, Request

from app.contracts.drafts import DraftCreate, DraftUpdate, JourneyDraft
from app.contracts.journey import BaseRevision
from app.modules.admission.service import InferenceIdentity
from app.modules.requests.http import idempotency_key
from app.modules.sessions.http import require_session
from app.modules.auth.http import require_member

router = APIRouter(tags=['체험'])


@router.post('/journeys/{journey_id}/drafts', response_model=JourneyDraft, status_code=201, operation_id='createJourneyDraft')
async def create_draft(journey_id: UUID, request: Request, body: DraftCreate):
    session = await require_session(request, user_activity=True)
    peer = request.client.host if request.client else ''
    account = await require_member(request) if session.user_id is not None else None
    await request.app.state.admission_service.check_http(peer, session.subject_id)
    return await request.app.state.draft_service.create(session, InferenceIdentity(session.subject_id, peer, account.id if account else None),
        journey_id, idempotency_key(request), body)


@router.patch('/journeys/{journey_id}/drafts/{draft_id}', response_model=JourneyDraft, operation_id='updateJourneyDraft')
async def update_draft(journey_id: UUID, draft_id: UUID, request: Request, body: DraftUpdate):
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(request.client.host if request.client else '', session.subject_id)
    return await request.app.state.draft_service.update(session, journey_id, draft_id, body)


@router.post('/journeys/{journey_id}/drafts/{draft_id}/approve', response_model=JourneyDraft, operation_id='approveJourneyDraft')
async def approve_draft(journey_id: UUID, draft_id: UUID, request: Request, body: BaseRevision):
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(request.client.host if request.client else '', session.subject_id)
    return await request.app.state.draft_service.approve(session, journey_id, draft_id, body.base_revision)
