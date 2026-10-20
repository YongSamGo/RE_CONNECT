"""익명 공개 공고 읽기. 구체 DB 구현은 앱 조립에서 주입한다."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.modules.opportunities.service import OpportunityPage, OpportunitySearch, PublicOpportunity

router = APIRouter(tags=["공고"])


@router.get("/opportunities", response_model=OpportunityPage, operation_id="listOpportunities")
def list_opportunities(request: Request, response: Response, search: Annotated[OpportunitySearch, Query()]):
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.opportunity_service.list(search)


@router.get("/opportunities/{opportunity_id}", response_model=PublicOpportunity, operation_id="getOpportunity")
def get_opportunity(opportunity_id: UUID, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.opportunity_service.get(opportunity_id)
