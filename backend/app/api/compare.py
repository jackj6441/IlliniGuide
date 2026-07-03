from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas import CompareRequest, CompareResponse
from app.services.advising_service import build_compare_response

router = APIRouter(prefix="/api", tags=["compare"])


@router.post("/compare", response_model=CompareResponse)
async def compare(
    request: CompareRequest,
    db_session: Session = Depends(get_db_session),
) -> CompareResponse:
    return build_compare_response(request, db_session)
