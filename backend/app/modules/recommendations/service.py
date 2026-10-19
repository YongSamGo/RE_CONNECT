"""소유한 최신 확정본과 공개 공고를 재검사하는 비저장 추천 서비스."""

import asyncio
from typing import Annotated

from pydantic import BaseModel, Field

from app.contracts.fields import CONTRACT_CONFIG
from app.contracts.journey import ProfileRef
from app.contracts.recommendation import EligibilitySummary, RecommendationMatch, RecommendationRequest
from app.contracts.time import UtcDatetime, utc_now
from app.core.business_errors import AppError
from app.modules.journeys.service import JourneyService
from app.modules.opportunities.service import OpportunitySummary, PublicOpportunityService
from app.modules.recommendations.filters import filter_candidates
from app.modules.recommendations.ranking import rank_candidates
from app.modules.roles.service import RoleService
from app.modules.sessions.service import Session


class Recommendation(BaseModel):
    model_config = CONTRACT_CONFIG
    rank: int = Field(ge=1)
    opportunity: OpportunitySummary
    matched: RecommendationMatch
    eligibility: EligibilitySummary


class RecommendationList(BaseModel):
    model_config = CONTRACT_CONFIG
    profile: ProfileRef
    generated_at: UtcDatetime
    based_on_previous_confirmed: bool
    items: Annotated[list[Recommendation], Field(max_length=20)]


class RecommendationService:
    def __init__(self, journeys: JourneyService, opportunities: PublicOpportunityService, roles: RoleService):
        self.journeys, self.opportunities, self.roles = journeys, opportunities, roles

    async def create(self, session: Session, body: RecommendationRequest) -> RecommendationList:
        snapshot = await self.journeys.resolve_profile(session, body.profile, require_current=True)
        state = await self.journeys.role_state(session, body.profile.id)
        view = await self.journeys.profile(session, body.profile.id)
        if state.profile_version != snapshot.reference.version or state.revision != view.revision:
            raise AppError("VERSION_CONFLICT")
        now = utc_now()
        opportunities = await asyncio.to_thread(self.opportunities.recommendation_candidates, now)
        catalog = await self.roles.catalog_entries()
        try:
            candidates = filter_candidates(snapshot.content, opportunities, body.filters, frozenset(state.role_ids), now)
            ranked = await asyncio.to_thread(rank_candidates, snapshot.content, candidates, catalog)
        except ValueError:
            raise AppError("SERVICE_UNAVAILABLE") from None
        # DB/Redis의 분산 트랜잭션은 아니다. 반환 직전 현재 소유권·수명·버전·제외 선택을 다시 읽는다.
        for item in ranked:
            latest = await asyncio.to_thread(self.opportunities.get, item.candidate.opportunity.id)
            if latest != item.candidate.opportunity:
                raise AppError("VERSION_CONFLICT")
            if not filter_candidates(snapshot.content, [latest], body.filters, frozenset(state.role_ids), utc_now()):
                raise AppError("VERSION_CONFLICT")
        await self.journeys.resolve_profile(session, body.profile, require_current=True)
        if (await self.journeys.role_state(session, body.profile.id)).revision != state.revision:
            raise AppError("VERSION_CONFLICT")
        fields = set(OpportunitySummary.model_fields)
        return RecommendationList(profile=snapshot.reference, generated_at=utc_now(),
            based_on_previous_confirmed=view.has_unconfirmed_changes,
            items=[Recommendation(rank=index, opportunity=OpportunitySummary.model_validate(
                item.candidate.opportunity.model_dump(include=fields)), matched=item.matched,
                eligibility=EligibilitySummary(overall=item.candidate.eligibility.overall,
                    no_requirements=item.candidate.eligibility.no_requirements,
                    needs_review_count=sum(c.status == "unknown" for c in item.candidate.eligibility.conditions)))
                for index, item in enumerate(ranked, 1)])
