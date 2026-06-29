from fastapi import APIRouter

from app.schemas import RecommendRequest, RecommendResponse
from app.services.advising_service import build_mock_recommend_response

router = APIRouter(prefix="/api", tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(request: RecommendRequest) -> RecommendResponse:
    return build_mock_recommend_response(request)
