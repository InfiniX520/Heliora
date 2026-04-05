"""Lightweight chat intent and reply generation for Day-1 flow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatDecision:
    """Deterministic chat decision object."""

    intent: str
    confidence: float
    reply: str
    suggested_actions: list[str]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def detect_intent(content: str) -> tuple[str, float]:
    """Detect a coarse intent label from user content."""
    lowered = content.lower()

    task_keywords = ("task", "todo", "plan", "安排", "任务", "计划")
    memory_keywords = ("memory", "remember", "recall", "记得", "回忆", "复盘")
    status_keywords = ("status", "progress", "做到哪", "进度", "状态", "完成")

    if _contains_any(lowered, task_keywords):
        return "task_planning", 0.93
    if _contains_any(lowered, memory_keywords):
        return "memory_recall", 0.88
    if _contains_any(lowered, status_keywords):
        return "status_check", 0.84
    return "general_chat", 0.72


def build_reply(intent: str, content: str) -> str:
    """Build deterministic response text for current scaffold stage."""
    snippet = content.strip().replace("\n", " ")[:120]

    if intent == "task_planning":
        return (
            "I detected a task-planning intent. "
            "You can call /api/v1/tasks/submit for async execution. "
            f"Summary: {snippet}"
        )
    if intent == "memory_recall":
        return (
            "I detected a memory-recall intent. "
            "You can call /api/v1/memory/retrieve to fetch related context. "
            f"Summary: {snippet}"
        )
    if intent == "status_check":
        return (
            "I detected a status-check intent. "
            "You can call /api/v1/tasks/{task_id} to query task status. "
            f"Summary: {snippet}"
        )
    return f"Message received. Summary: {snippet}"


def suggested_actions_for_intent(intent: str) -> list[str]:
    """Provide stable action hints based on intent."""
    if intent == "task_planning":
        return ["open_task_submit", "set_priority", "attach_payload"]
    if intent == "memory_recall":
        return ["open_memory_retrieve", "set_scope", "set_top_k"]
    if intent == "status_check":
        return ["open_task_query", "check_task_id"]
    return ["continue_chat"]


def decide_chat(content: str) -> ChatDecision:
    """Return a deterministic chat decision from content."""
    intent, confidence = detect_intent(content)
    return ChatDecision(
        intent=intent,
        confidence=confidence,
        reply=build_reply(intent, content),
        suggested_actions=suggested_actions_for_intent(intent),
    )
