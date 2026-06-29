from fastapi import APIRouter

from app.schemas import ChatRequest, ChatResponse
from app.services.advising_service import build_mock_chat_response

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return build_mock_chat_response(request)
