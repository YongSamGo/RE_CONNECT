"""확정 후 역할 후보. 개인 결과를 공개 캐시하거나 임의 후보로 대신하지 않는다."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.contracts.roles import RoleCandidates
from app.modules.sessions.http import require_session

router = APIRouter(tags=["역할"])


@router.get("/journeys/{journey_id}/roles", response_model=RoleCandidates, operation_id="getRoleCandidates")
async def get_roles(journey_id: UUID, request: Request, profile_version: Annotated[int | None, Query(ge=1)] = None):
    session = await require_session(request)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    return await request.app.state.role_service.candidates(session, journey_id, profile_version)
