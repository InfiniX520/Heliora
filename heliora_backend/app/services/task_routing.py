"""Task routing policy and SLA selection helpers."""

from __future__ import annotations

from app.core.config import settings


MEMORY_TASK_TYPES = {
    "memory.retrieve",
    "memory.feedback",
    "memory.rollback",
    "memory.delete",
    "memory.conflict_review",
}

QUEUE_BY_PRIORITY = {
    "P0": "realtime.queue",
    "P1": "realtime.queue",
    "P2": "normal.queue",
    "P3": "batch.queue",
}


def is_memory_task(task_type: str, required_capabilities: list[str]) -> bool:
    """Return true when task should be routed to memory queue."""
    normalized_type = task_type.strip().lower()
    if normalized_type in MEMORY_TASK_TYPES:
        return True
    if normalized_type.startswith("memory.") or normalized_type.startswith("memory_"):
        return True

    capabilities = {cap.strip().lower() for cap in required_capabilities}
    return "memory" in capabilities or "memory_service" in capabilities


def select_queue_and_sla(priority: str, task_type: str, required_capabilities: list[str]) -> tuple[str, int]:
    """Select target queue and SLA milliseconds for one task."""
    if is_memory_task(task_type, required_capabilities):
        return ("memory.queue", settings.task_queue_sla_memory_ms)

    normalized_priority = priority.strip().upper()
    queue = QUEUE_BY_PRIORITY.get(normalized_priority, "normal.queue")
    sla_by_priority = {
        "P0": settings.task_queue_sla_p0_ms,
        "P1": settings.task_queue_sla_p1_ms,
        "P2": settings.task_queue_sla_p2_ms,
        "P3": settings.task_queue_sla_p3_ms,
    }
    return (queue, sla_by_priority.get(normalized_priority, settings.task_queue_sla_p2_ms))
