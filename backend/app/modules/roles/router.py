"""확정 후 역할 후보. 개인 결과를 공개 캐시하거나 임의 후보로 대신하지 않는다."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.contracts.roles import RoleCandidates, RoleExclusionUpdate, RoleExclusions
from app.core.errors import FieldError, error_response
from app.modules.roles.service import UnknownRoleIds
from app.modules.sessions.http import require_session

router = APIRouter(tags=["역할"])


@router.get("/journeys/{journey_id}/role-exclusions", response_model=RoleExclusions, operation_id="getRoleExclusions")
async def get_exclusions(journey_id: UUID, request: Request):
    session = await require_session(request)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    return await request.app.state.role_service.exclusions(session, journey_id)


@router.get("/journeys/{journey_id}/roles", response_model=RoleCandidates, operation_id="getRoleCandidates")
async def get_roles(journey_id: UUID, request: Request, profile_version: Annotated[int | None, Query(ge=1)] = None):
    session = await require_session(request)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    return await request.app.state.role_service.candidates(session, journey_id, profile_version)


@router.put("/journeys/{journey_id}/role-exclusions", response_model=RoleExclusions, operation_id="putRoleExclusions")
async def put_exclusions(journey_id: UUID, request: Request, body: RoleExclusionUpdate):
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    try:
        return await request.app.state.role_service.set_exclusions(session, journey_id, body)
    except UnknownRoleIds as error:
        return error_response(request, 422, "VALIDATION_FAILED", fields=[
            FieldError(path=f"role_ids[{index}]", reason="invalid_value") for index in error.indices
        ])
