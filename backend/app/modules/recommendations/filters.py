"""공개본·수명·프로필·전체 자격을 먼저 검사한다. 점수로 필수조건을 완화하지 않는다."""

from dataclasses import dataclass
from datetime import datetime

from app.contracts.profile import ProfileContent
from app.contracts.recommendation import RecommendationFilters
from app.contracts.regions import Region
from app.core.business_errors import AppError
from app.modules.eligibility.evaluator import Evaluation, evaluate
from app.modules.opportunities.lifecycle import assess_lifecycle
from app.modules.opportunities.service import PublicOpportunity


@dataclass(frozen=True)
class Candidate:
    opportunity: PublicOpportunity
    eligibility: Evaluation


def region_matches(region: Region | None, choices: list[Region]) -> bool:
    return region is not None and any(
        choice.province == region.province and (choice.district is None or choice.district == region.district)
        for choice in choices
    )


def filter_candidates(profile: ProfileContent, opportunities: list[PublicOpportunity], filters: RecommendationFilters,
                      excluded: frozenset[str], now: datetime) -> list[Candidate]:
    if profile.missing_for_recommendation():
        raise AppError("PROFILE_NOT_CONFIRMED")
    candidates = []
    for opportunity in opportunities:
        if opportunity.change_pending or not assess_lifecycle(opportunity, source_checked_at=opportunity.source_checked_at,
                                                             now=now).recommendation_allowed:
            continue
        if opportunity.activity_type not in profile.activity_types:
            continue
        if filters.activity_types is not None and opportunity.activity_type not in filters.activity_types:
            continue
        if opportunity.remote_allowed is not True:
            if not region_matches(opportunity.activity_region, profile.preferred_regions):
                continue
            if filters.regions is not None and not region_matches(opportunity.activity_region, filters.regions):
                continue
        if profile.paid_preference in ("paid", "unpaid") and opportunity.paid is not (profile.paid_preference == "paid"):
            continue
        if filters.paid is not None and opportunity.paid is not filters.paid:
            continue
        # 복합 역할도 제외한 역할 하나와 겹치면 공고 전체를 제외한다.
        if excluded.intersection(opportunity.role_tags):
            continue
        try:
            eligibility = evaluate(profile, opportunity.requirements)
        except ValueError:
            raise AppError("SERVICE_UNAVAILABLE") from None
        if eligibility.structural_issues:
            raise AppError("SERVICE_UNAVAILABLE")
        if eligibility.overall != "not_satisfied":
            candidates.append(Candidate(opportunity, eligibility))
    return candidates
