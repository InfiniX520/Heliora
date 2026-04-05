"""Chat endpoints."""

from uuid import uuid4

from fastapi import APIRouter, Request

from app.api.deps import enforce_security_mode
from app.core.config import settings
from app.core.errors import HelioraError
from app.core.response import success_response
from app.schemas.chat import ChatRequest
from app.services.chat_engine import decide_chat
from app.services.chat_sessions import chat_session_store


router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(request: Request, body: ChatRequest) -> dict:
    """Process Day-1 chat flow with intent extraction and action hints."""
    enforce_security_mode(request)

    content = body.content.strip()
    if not content:
        raise HelioraError(
            code="INVALID_ARGUMENT",
            status_code=400,
            message="content cannot be blank after trimming",
        )

    if len(content) > settings.chat_max_content_chars:
        raise HelioraError(
            code="CONTENT_TOO_LONG",
            status_code=400,
            message=f"content exceeds limit: {settings.chat_max_content_chars}",
            details={"max_chars": settings.chat_max_content_chars},
        )

    decision = decide_chat(content)
    turn_index = chat_session_store.record_turn(body.session_id)

    data = {
        "message_id": f"msg_{uuid4().hex[:8]}",
        "content": decision.reply,
        "intent": decision.intent,
        "confidence": decision.confidence,
        "suggested_actions": decision.suggested_actions,
        "turn_index": turn_index,
        "references": [],
        "memory_hits": [],
        "session_id": body.session_id,
    }
    return success_response(request, data=data)
