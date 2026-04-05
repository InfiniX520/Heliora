"""Schemas for task endpoints."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskSubmitRequest(BaseModel):
    """Incoming task submit payload."""

    task_type: str = Field(min_length=1)
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    required_capabilities: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskConsumeRequest(BaseModel):
    """Request payload for consuming one queued task."""

    queue: str | None = None
    force_fail: bool = False


class TaskCancelRequest(BaseModel):
    """Request payload for canceling one task."""

    reason: str | None = Field(default=None, max_length=256)
