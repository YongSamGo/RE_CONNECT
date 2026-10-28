"""운영자 감사 기록 조회 경로. 호출마다 서버가 세션·운영자 역할·MFA를 다시 확인한다."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query, Request
from starlette.responses import JSONResponse

from app.modules.audit.models import AuditList, AuditSearch
from app.modules.auth.http import require_operator

router = APIRouter(tags=["운영자"])


@router.get("/admin/audit", response_model=AuditList, operation_id="listAudit")
async def list_audit(request: Request, search: Annotated[AuditSearch, Query()]):
    await require_operator(request)
    result = await asyncio.to_thread(request.app.state.audit_service.page, search)
    return JSONResponse(result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})
