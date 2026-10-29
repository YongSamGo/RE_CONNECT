"""공고 오류 신고 경로. 접수는 세션 주체 기준, 처리는 호출마다 운영자 역할·MFA를 서버에서 확인한다.

CSRF·Origin·입력 크기는 공통 미들웨어가 먼저 막는다. 화면 숨김에 기대지 않는다.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from starlette.responses import JSONResponse

from app.core.business_errors import AppError
from app.core.request_id import get_request_id
from app.modules.reports.models import AdminReport, AdminReportList, ReportCreate, ReportReceipt, ReportStatus, ReportUpdate
from app.modules.requests.http import idempotency_key
from app.modules.sessions.http import require_session

router = APIRouter()


def _peer(request: Request) -> str:
    return request.client.host if request.client else ""


async def _operator(request: Request):
    session = await require_session(request, user_activity=True, validate_member=False)
    await request.app.state.admission_service.check_http(_peer(request), session.subject_id)
    return await request.app.state.member_service.require(session, operator=True)


@router.post("/reports", response_model=ReportReceipt, status_code=201, operation_id="createReport", tags=["공고"])
async def create_report(request: Request, body: ReportCreate):
    if request.query_params:
        raise AppError("VALIDATION_FAILED")
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(_peer(request), session.subject_id)
    result = await request.app.state.report_service.create(session.subject_id, _peer(request), idempotency_key(request), body)
    return JSONResponse(result.model_dump(mode="json"), status_code=201, headers={"Cache-Control": "no-store"})


@router.get("/admin/reports", response_model=AdminReportList, operation_id="listReports", tags=["운영자"])
async def list_reports(request: Request, status: ReportStatus | None = None,
                       page: Annotated[int, Query(ge=1, le=2**31 - 1)] = 1, page_size: Annotated[int, Query(ge=1, le=20)] = 20):
    if set(request.query_params) - {"status", "page", "page_size"} or any(len(request.query_params.getlist(name)) > 1 for name in request.query_params):
        raise AppError("VALIDATION_FAILED")
    await _operator(request)
    result = await request.app.state.report_service.listing(status, page, page_size)
    return JSONResponse(result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


@router.patch("/admin/reports/{report_id}", response_model=AdminReport, operation_id="updateReport", tags=["운영자"])
async def update_report(report_id: UUID, request: Request, body: ReportUpdate):
    if request.query_params:
        raise AppError("VALIDATION_FAILED")
    account = await _operator(request)
    result = await request.app.state.report_service.update(report_id, body, actor_id=account.id, request_id=get_request_id(request))
    return JSONResponse(result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})
