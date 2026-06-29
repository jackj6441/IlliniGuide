from fastapi import APIRouter

from app.schemas import CompareRequest, CompareResponse
from app.services.advising_service import build_mock_compare_response

router = APIRouter(prefix="/api", tags=["compare"])


@router.post("/compare", response_model=CompareResponse)
async def compare(request: CompareRequest) -> CompareResponse:
    return build_mock_compare_response(request)
