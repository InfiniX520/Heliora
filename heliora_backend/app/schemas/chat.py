"""Schemas for chat endpoints."""

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat payload."""

    session_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    context: dict[str, Any] | None = None
