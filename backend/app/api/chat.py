from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas import ChatRequest, ChatResponse
from app.services.advising_service import build_mock_chat_response

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db_session: Session = Depends(get_db_session),
) -> ChatResponse:
    return build_mock_chat_response(request, db_session)
