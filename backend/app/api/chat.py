from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas import ChatRequest, ChatResponse
from app.services.advising_service import (
    build_chat_response,
    build_chat_response_stream,
)

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db_session: Session = Depends(get_db_session),
) -> ChatResponse:
    return await build_chat_response(request, db_session)


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    db_session: Session = Depends(get_db_session),
) -> StreamingResponse:
    return StreamingResponse(
        build_chat_response_stream(request, db_session),
        media_type="text/event-stream",
        headers={
            # Disable buffering at proxies/CDN so the client sees tokens as
            # they are generated. nginx honours X-Accel-Buffering=no.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
