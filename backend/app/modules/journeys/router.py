"""실제 익명 체험 생성. 세션/CSRF/현재 동의/분당 한도 뒤에 하루 한도를 확정한다."""

from fastapi import APIRouter, Request, Response

from app.contracts.journey import Journey, JourneyCreate, ProfileDraftView, ProfileUpdate, BaseRevision, ProfileConfirmResult, MessageCreate, MessageResult
from app.core.errors import FieldError, error_response
from app.modules.journeys.service import MissingProfileFields
from uuid import UUID
from app.modules.admission.service import InferenceIdentity
from app.modules.requests.http import idempotency_key
from app.modules.sessions.http import require_session

router = APIRouter(tags=["체험"])


@router.post('/journeys/{journey_id}/messages', response_model=MessageResult, operation_id='createMessage')
async def create_message(journey_id: UUID, request: Request, body: MessageCreate):
    session = await require_session(request, user_activity=True)
    peer = request.client.host if request.client else ''
    await request.app.state.admission_service.check_http(peer, session.subject_id)
    return await request.app.state.journey_message_service.send(session, InferenceIdentity(session.subject_id, peer),
        journey_id, idempotency_key(request), body)


@router.delete("/journeys/{journey_id}", status_code=204, operation_id="deleteJourney")
async def end_journey(journey_id: UUID, request: Request):
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    await request.app.state.journey_service.end(session, journey_id)
    return Response(status_code=204)


@router.post("/journeys", response_model=Journey, status_code=201, operation_id="createJourney")
async def create_journey(request: Request, body: JourneyCreate):
    session = await require_session(request, user_activity=True)
    peer = request.client.host if request.client else ""
    await request.app.state.admission_service.check_http(peer, session.subject_id)
    return await request.app.state.journey_service.create(session, InferenceIdentity(session.subject_id, peer),
                                                           idempotency_key(request), body)


@router.get("/journeys/{journey_id}/profile", response_model=ProfileDraftView, operation_id="getJourneyProfile")
async def get_profile(journey_id: UUID, request: Request):
    session = await require_session(request)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    return await request.app.state.journey_service.profile(session, journey_id)


@router.patch("/journeys/{journey_id}/profile", response_model=ProfileDraftView, operation_id="updateJourneyProfile")
async def update_profile(journey_id: UUID, request: Request, body: ProfileUpdate):
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    return await request.app.state.journey_service.update_profile(session, journey_id, body)


@router.post("/journeys/{journey_id}/profile/confirm", response_model=ProfileConfirmResult, operation_id="confirmJourneyProfile")
async def confirm_profile(journey_id: UUID, request: Request, body: BaseRevision):
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    try:
        return await request.app.state.journey_service.confirm_profile(session, journey_id, body.base_revision)
    except MissingProfileFields as error:
        return error_response(request, 422, "VALIDATION_FAILED", fields=[
            FieldError(path=f"draft.{name}", reason="required") for name in error.fields
        ])
