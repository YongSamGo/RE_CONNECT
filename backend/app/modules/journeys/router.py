"""실제 익명 체험 생성. 세션/CSRF/현재 동의/분당 한도 뒤에 하루 한도를 확정한다."""

from fastapi import APIRouter, Request

from app.contracts.journey import Journey, JourneyCreate
from app.modules.admission.service import InferenceIdentity
from app.modules.requests.http import idempotency_key
from app.modules.sessions.http import require_session

router = APIRouter(tags=["체험"])


@router.post("/journeys", response_model=Journey, status_code=201, operation_id="createJourney")
async def create_journey(request: Request, body: JourneyCreate):
    session = await require_session(request, user_activity=True)
    peer = request.client.host if request.client else ""
    await request.app.state.admission_service.check_http(peer, session.subject_id)
    return await request.app.state.journey_service.create(session, InferenceIdentity(session.subject_id, peer),
                                                           idempotency_key(request), body)
