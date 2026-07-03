from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas import RecommendRequest, RecommendResponse
from app.services.advising_service import build_recommend_response

router = APIRouter(prefix="/api", tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(
    request: RecommendRequest,
    db_session: Session = Depends(get_db_session),
) -> RecommendResponse:
    return build_recommend_response(request, db_session)
