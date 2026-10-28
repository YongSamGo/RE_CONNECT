"""자기 자료 삭제·동의 철회·재인증 탈퇴. 주체와 삭제 대상은 서버가 정한다."""

import secrets
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, Response

from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.modules.deletions.models import WithdrawRequest, WithdrawResult
from app.modules.sessions.http import require_session, write_csrf_cookie, write_session_cookie
from app.modules.sessions.service import IssuedSession, StoreUnavailable, csrf_token, token_digest

router = APIRouter(tags=['회원 저장'])


def cookies(request, response, issued):
    if issued is None: return response
    write_session_cookie(request, response, issued)
    write_csrf_cookie(request, response, csrf_token(issued.session), issued.session)
    return response


async def member_delete(request, action, document_id=None):
    if request.query_params or await request.body(): raise AppError('VALIDATION_FAILED')
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(request.client.host if request.client else '', session.subject_id)
    return await request.app.state.deletion_service.request(session, action, document_id)


@router.delete('/profiles/me', status_code=204, operation_id='deleteSavedProfile')
async def profile(request: Request):
    _, _, issued = await member_delete(request, 'profile_delete')
    return cookies(request, Response(status_code=204, headers={'Cache-Control': 'no-store'}), issued)


@router.delete('/drafts/{document_id}', status_code=204, operation_id='deleteSavedDraft')
async def application(document_id: UUID, request: Request):
    _, _, issued = await member_delete(request, 'application_delete', document_id)
    return cookies(request, Response(status_code=204, headers={'Cache-Control': 'no-store'}), issued)


@router.delete('/me', status_code=204, operation_id='deleteAccount')
async def account(request: Request):
    _, _, issued = await member_delete(request, 'account_delete')
    return cookies(request, Response(status_code=204, headers={'Cache-Control': 'no-store'}), issued)


@router.post('/consents/withdraw', response_model=WithdrawResult, operation_id='withdrawConsent')
async def withdraw(request: Request, body: WithdrawRequest):
    if request.query_params: raise AppError('VALIDATION_FAILED')
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(request.client.host if request.client else '', session.subject_id)
    if session.user_id is None:
        if body.purpose != 'ai_processing': raise AppError('UNAUTHENTICATED')
        token = secrets.token_urlsafe(32)
        try:
            replacement, journeys = await request.app.state.member_service.store.switch(session.digest, token_digest(token),
                uuid4(), secrets.token_hex(32), with_counts=True)
        except StoreUnavailable:
            raise AppError('SERVICE_UNAVAILABLE') from None
        if replacement is None: raise AppError('SESSION_EXPIRED')
        issued = IssuedSession(replacement, token)
        result = WithdrawResult(purpose=body.purpose, withdrawn_at=utc_now(),
            deleted={'journeys': journeys, 'profile_versions': 0, 'documents': 0})
    else:
        action = 'ai_withdraw' if body.purpose == 'ai_processing' else 'storage_withdraw'
        event, deleted, issued = await request.app.state.deletion_service.request(session, action)
        result = WithdrawResult(purpose=body.purpose, withdrawn_at=event.deleted_at if event else utc_now(), deleted=deleted)
    return cookies(request, JSONResponse(result.model_dump(mode='json'), headers={'Cache-Control': 'no-store'}), issued)
