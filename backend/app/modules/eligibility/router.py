"""확정 참조만 받는 사적 자격 대조 API. 결과는 사용자와 원문 근거의 규칙 비교다."""

from uuid import UUID

from fastapi import APIRouter, Request

from app.contracts.eligibility import EligibilityRequest, EligibilityResult
from app.modules.sessions.http import require_session

router = APIRouter(tags=["자격"])


@router.post("/opportunities/{opportunity_id}/eligibility", response_model=EligibilityResult, operation_id="checkEligibility")
async def check_eligibility(opportunity_id: UUID, request: Request, body: EligibilityRequest):
    # 조회 성격의 대조 요청은 자동 재조회로 유휴 시간을 연장하지 않는다.
    session = await require_session(request)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    return await request.app.state.eligibility_service.check(session, opportunity_id, body)
