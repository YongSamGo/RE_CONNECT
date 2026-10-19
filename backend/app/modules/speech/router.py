"""읽어주기용 버전 참조 API. 자유 text·모델·화자·URL은 받지 않는다."""

from fastapi import APIRouter, Request, Response

from app.contracts.speech import SpeechRequest
from app.modules.admission.service import InferenceIdentity
from app.modules.requests.http import idempotency_key
from app.modules.sessions.http import require_session

router = APIRouter(tags=['음성'])


@router.post('/speech', operation_id='createSpeech')
async def read_aloud(request: Request, body: SpeechRequest):
    session = await require_session(request, user_activity=True)
    peer = request.client.host if request.client else ''
    await request.app.state.admission_service.check_http(peer, session.subject_id)
    audio, count = await request.app.state.speech_service.read(session, InferenceIdentity(session.subject_id, peer), idempotency_key(request), body)
    return Response(content=audio, media_type='audio/wav', headers={'X-Speech-Segment-Count': str(count)})
