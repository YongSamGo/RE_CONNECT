"""운영자 공고 목록·등록·상세·수정. 모든 요청은 현재 DB 역할과 운영자 MFA를 매번 확인한다.

변경 요청의 Origin·CSRF·본문 크기는 RequestSecurityMiddleware가 먼저 검사한다.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from starlette.responses import JSONResponse

from app.core.request_id import get_request_id
from app.modules.admin_opportunities.models import (
    AdminOpportunity, AdminOpportunityList, AdminOpportunitySearch, OpportunityCreate, OpportunityPatch,
)
from app.modules.requests.http import idempotency_key
from app.modules.sessions.http import require_session

router = APIRouter(tags=["운영자"])
NO_STORE = {"Cache-Control": "no-store"}


async def require_operator(request: Request):
    session = await require_session(request, user_activity=True, validate_member=False)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    # 역할이 회수되었거나 MFA가 끝나지 않았으면 여기서 403이다(#52 연결 전에는 항상 MFA_REQUIRED).
    return await request.app.state.member_service.require(session, operator=True)


@router.get("/admin/opportunities", response_model=AdminOpportunityList, operation_id="listAdminOpportunities")
async def list_admin_opportunities(request: Request, search: Annotated[AdminOpportunitySearch, Query()]):
    await require_operator(request)
    result = await request.app.state.admin_opportunity_service.list(search)
    return JSONResponse(result.model_dump(mode="json"), headers=NO_STORE)


@router.post("/admin/opportunities", status_code=201, response_model=AdminOpportunity, operation_id="createAdminOpportunity")
async def create_admin_opportunity(request: Request, body: OpportunityCreate):
    account = await require_operator(request)
    result = await request.app.state.admin_opportunity_service.create(account.id, idempotency_key(request), body, get_request_id(request))
    return JSONResponse(result.model_dump(mode="json"), status_code=201, headers=NO_STORE)


@router.get("/admin/opportunities/{opportunity_id}", response_model=AdminOpportunity, operation_id="getAdminOpportunity")
async def get_admin_opportunity(opportunity_id: UUID, request: Request):
    await require_operator(request)
    result = await request.app.state.admin_opportunity_service.get(opportunity_id)
    return JSONResponse(result.model_dump(mode="json"), headers=NO_STORE)


@router.patch("/admin/opportunities/{opportunity_id}", response_model=AdminOpportunity, operation_id="updateAdminOpportunity")
async def update_admin_opportunity(opportunity_id: UUID, request: Request, body: OpportunityPatch):
    account = await require_operator(request)
    result = await request.app.state.admin_opportunity_service.update(account.id, opportunity_id, body, get_request_id(request))
    return JSONResponse(result.model_dump(mode="json"), headers=NO_STORE)
