"""Tests for task routing policy and SLA selection."""

import pytest

from app.core.config import settings
from app.services.task_routing import is_memory_task, select_queue_and_sla


@pytest.mark.parametrize(
    ("priority", "expected_queue"),
    [
        ("P0", "realtime.queue"),
        ("P1", "realtime.queue"),
        ("P2", "normal.queue"),
        ("P3", "batch.queue"),
        ("unknown", "normal.queue"),
    ],
)
def test_select_queue_by_priority(priority: str, expected_queue: str) -> None:
    queue, _ = select_queue_and_sla(priority, "course.plan.generate", ["planner"])

    assert queue == expected_queue


def test_memory_task_type_routes_to_memory_queue() -> None:
    queue, sla_ms = select_queue_and_sla("P3", "memory.feedback", ["planner"])

    assert queue == "memory.queue"
    assert sla_ms == settings.task_queue_sla_memory_ms


def test_memory_capability_routes_to_memory_queue() -> None:
    queue, _ = select_queue_and_sla("P2", "course.plan.generate", ["memory_service"])

    assert queue == "memory.queue"


def test_select_queue_uses_configured_sla(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "task_queue_sla_p2_ms", 22222)

    queue, sla_ms = select_queue_and_sla("P2", "course.plan.generate", ["planner"])

    assert queue == "normal.queue"
    assert sla_ms == 22222


def test_is_memory_task_matches_prefix() -> None:
    assert is_memory_task("memory.custom.op", ["planner"]) is True
    assert is_memory_task("course.plan.generate", ["planner"]) is False
