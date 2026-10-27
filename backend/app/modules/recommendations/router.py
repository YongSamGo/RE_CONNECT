"""AI를 호출하지 않는 개인 추천. CSRF와 세션/소유권을 검사한다."""

from fastapi import APIRouter, Request

from app.contracts.recommendation import RecommendationRequest
from app.modules.recommendations.service import RecommendationList
from app.modules.sessions.http import require_session

router = APIRouter(tags=["공고"])


@router.post("/recommendations", response_model=RecommendationList, operation_id="createRecommendations")
async def create_recommendations(request: Request, body: RecommendationRequest):
    session = await require_session(request, user_activity=True)
    await request.app.state.admission_service.check_http(request.client.host if request.client else "", session.subject_id)
    return await request.app.state.recommendation_service.create(session, body)
