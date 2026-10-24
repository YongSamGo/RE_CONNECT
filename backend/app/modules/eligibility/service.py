"""소유한 최신 확정본과 현재 공개 공고의 규칙 대조. 모델/판정 캐시/저장은 없다."""

import asyncio
from uuid import UUID

from app.contracts.eligibility import ConditionEvaluation, EligibilityRequest, EligibilityResult, GroupEvaluation
from app.contracts.preparation import OpportunityRef
from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.modules.eligibility.evaluator import evaluate
from app.modules.journeys.service import JourneyService
from app.modules.opportunities.service import PublicOpportunityService
from app.modules.sessions.service import Session

_PROFILE_FIELDS = {
    "age": "birth_year", "residence_region": "residence_region", "certification": "certifications",
    "completed_course": "completed_courses", "weekday": "available_weekdays", "hours_per_week": "hours_per_week",
}
_REASONS = {
    "missing_value": "missing_profile_value", "needs_review": "unclear_requirement",
    "name_equivalence_unverified": "unclear_requirement", "district_unconfirmed": "missing_profile_value",
    "missing_reference_date": "reference_date_missing", "age_boundary": "age_boundary",
    "invalid_birth_year": "unclear_requirement",
}


class EligibilityService:
    def __init__(self, journeys: JourneyService, opportunities: PublicOpportunityService):
        self.journeys, self.opportunities = journeys, opportunities

    async def check(self, session: Session, opportunity_id: UUID, body: EligibilityRequest) -> EligibilityResult:
        snapshot = await self.journeys.resolve_profile(session, body.profile, require_current=True)
        opportunity = await asyncio.to_thread(self.opportunities.get, opportunity_id)
        if opportunity.version != body.opportunity_version:
            raise AppError("VERSION_CONFLICT")
        try:
            evaluation = evaluate(snapshot.content, opportunity.requirements)
        except ValueError:
            raise AppError("SERVICE_UNAVAILABLE") from None
        if evaluation.structural_issues or any(group.operator is None for group in evaluation.groups):
            # 공개 전 검증에서 거절되는 구조를 추측한 AND/OR로 바꾸지 않는다.
            raise AppError("SERVICE_UNAVAILABLE")
        conditions = []
        for requirement, compared in zip(opportunity.requirements, evaluation.conditions, strict=True):
            attribute = _PROFILE_FIELDS.get(requirement.field)
            value = getattr(snapshot.content, attribute) if attribute is not None else None
            reason = _REASONS.get(compared.reason) if compared.status == "unknown" else None
            if compared.status == "unknown" and reason is None:
                raise AppError("SERVICE_UNAVAILABLE")
            conditions.append(ConditionEvaluation(
                requirement_id=requirement.id, field=requirement.field, result=compared.status,
                user_value=value, source_evidence=requirement.source_evidence,
                review_reason=reason,
            ))
        # 서로 다른 저장소의 분산 트랜잭션은 아니다. 반환 직전에도 참조의 만료/변경을 검사한다.
        await self.journeys.resolve_profile(session, body.profile, require_current=True)
        latest = await asyncio.to_thread(self.opportunities.get, opportunity_id)
        if latest.version != opportunity.version:
            raise AppError("VERSION_CONFLICT")
        return EligibilityResult(
            profile=snapshot.reference, opportunity=OpportunityRef(id=opportunity.id, version=opportunity.version),
            overall=evaluation.overall, no_requirements=evaluation.no_requirements, conditions=conditions,
            groups=[GroupEvaluation(group_id=g.group_id, operator=g.operator, result=g.status) for g in evaluation.groups],
            evaluated_at=utc_now(),
        )
