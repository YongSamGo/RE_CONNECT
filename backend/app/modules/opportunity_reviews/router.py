"""운영자 공고 검수 경로. 호출마다 서버가 세션·운영자 역할·MFA를 다시 확인한다.

화면 숨김에 기대지 않는다. CSRF·Origin·입력 크기는 공통 미들웨어가 먼저 막는다.
"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from app.core.business_errors import AppError
from app.core.request_id import get_request_id
from app.modules.opportunity_reviews.models import ApproveRequest, CloseRequest, HideRequest, RejectRequest, ReviewResult
from app.modules.opportunity_reviews.service import NotPublishable
from app.modules.sessions.http import require_session

router = APIRouter(tags=["운영자"])
_PYDANTIC_TYPE = {"required": "missing", "invalid_value": "value_error"}


async def _operator(request: Request):
    if request.query_params:
        raise AppError("VALIDATION_FAILED")
    session = await require_session(request, user_activity=True, validate_member=False)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    return await request.app.state.member_service.require(session, operator=True)


async def _run(request: Request, action: str, opportunity_id: UUID, body) -> JSONResponse:
    account = await _operator(request)
    method = getattr(request.app.state.opportunity_review_service, action)
    try:
        result: ReviewResult = await asyncio.to_thread(method, opportunity_id, body, actor_id=account.id,
                                                       request_id=get_request_id(request))
    except NotPublishable as error:
        raise RequestValidationError([{"loc": ("body", *problem.path.split(".")), "type": _PYDANTIC_TYPE[problem.reason]}
                                      for problem in error.problems]) from None
    return JSONResponse(result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


@router.post("/admin/opportunities/{opportunity_id}/approve", response_model=ReviewResult, operation_id="approveOpportunity")
async def approve(opportunity_id: UUID, request: Request, body: ApproveRequest):
    return await _run(request, "approve", opportunity_id, body)


@router.post("/admin/opportunities/{opportunity_id}/reject", response_model=ReviewResult, operation_id="rejectOpportunity")
async def reject(opportunity_id: UUID, request: Request, body: RejectRequest):
    return await _run(request, "reject", opportunity_id, body)


@router.post("/admin/opportunities/{opportunity_id}/hide", response_model=ReviewResult, operation_id="hideOpportunity")
async def hide(opportunity_id: UUID, request: Request, body: HideRequest):
    return await _run(request, "hide", opportunity_id, body)


@router.post("/admin/opportunities/{opportunity_id}/close", response_model=ReviewResult, operation_id="closeOpportunity")
async def close(opportunity_id: UUID, request: Request, body: CloseRequest):
    return await _run(request, "close", opportunity_id, body)
