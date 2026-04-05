"""Schemas for memory endpoints."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class MemoryRetrieveRequest(BaseModel):
    """Incoming memory retrieve payload."""

    query: str = Field(min_length=1)
    scope: Literal["global", "course", "project", "thread"] = "project"
    top_k: int = Field(default=5, ge=1, le=20)
    context: dict[str, Any] | None = None
