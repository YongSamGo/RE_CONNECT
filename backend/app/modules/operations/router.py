"""내부 상태 확인 경로 (`/health/live`, `/health/ready`).

Compose 내부 전용이며 `/api/v1` 밖에 둔다. Nginx는 이 경로를 공개하지 않는다 (Plan/03 §1.1).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.modules.operations.readiness import Readiness, ReadinessService

router = APIRouter(prefix="/health", tags=["내부 상태"])


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"


def get_readiness_service(request: Request) -> ReadinessService:
    service: ReadinessService = request.app.state.readiness_service
    return service


@router.get("/live", response_model=Liveness)
async def health_live() -> Liveness:
    return Liveness()


@router.get(
    "/ready",
    response_model=Readiness,
    responses={503: {"model": Readiness, "description": "DB 또는 Redis 장애"}},
)
async def health_ready(
    service: Annotated[ReadinessService, Depends(get_readiness_service)],
) -> JSONResponse:
    readiness = await service.check()
    status_code = 503 if readiness.status == "unavailable" else 200
    return JSONResponse(
        status_code=status_code,
        content=readiness.model_dump(),
        headers={"Cache-Control": "no-store"},
    )
