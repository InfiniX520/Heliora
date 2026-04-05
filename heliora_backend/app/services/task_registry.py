"""In-memory task registry for scaffold-stage task lifecycle and audit checks."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from app.services.task_event_store import task_event_store
from app.services.task_state_store import task_state_store


FINAL_STATUSES = {"completed", "failed", "canceled"}
ALLOWED_TASK_TRANSITIONS: dict[str, set[str]] = {
    "created": {"routed"},
    "routed": {"queued"},
    "queued": {"running", "canceled"},
    "running": {"retrying", "completed", "failed", "canceled"},
    "retrying": {"running"},
    "completed": set(),
    "failed": set(),
    "canceled": set(),
}
logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InMemoryTaskRegistry:
    """Simple process-local task registry with audit event stream."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def _append_event_unlocked(
        self,
        *,
        task_id: str,
        event_type: str,
        from_status: str | None,
        to_status: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "event_id": f"evt_{uuid4().hex[:10]}",
            "task_id": task_id,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "message": message,
            "metadata": metadata or {},
            "ts": _utc_now_iso(),
        }
        self._events.setdefault(task_id, []).append(event)
        try:
            task_event_store.save_event(event)
        except Exception as exc:  # pragma: no cover - persistence fallback path
            logger.warning("task event persistence failed: %s", exc)
        return dict(event)

    def save_task(self, task: dict[str, Any]) -> None:
        task_id = str(task["task_id"])
        now = _utc_now_iso()
        record = dict(task)
        queued_status = str(record.get("status", "queued"))
        record.setdefault("status", queued_status)
        record.setdefault("created_at", now)
        record.setdefault("updated_at", now)
        record.setdefault("attempts", 0)
        with self._lock:
            self._tasks[task_id] = record
            try:
                task_state_store.save_task(record)
            except Exception as exc:  # pragma: no cover - persistence fallback path
                logger.warning("task state persistence failed on save: %s", exc)

            self._append_event_unlocked(
                task_id=task_id,
                event_type="created",
                from_status=None,
                to_status="created",
                message="task accepted",
                metadata={
                    "queue": record.get("queue"),
                    "sla_ms": record.get("sla_ms"),
                },
            )
            self._append_event_unlocked(
                task_id=task_id,
                event_type="routed",
                from_status="created",
                to_status="routed",
                message="task routed to target queue",
                metadata={
                    "queue": record.get("queue"),
                    "sla_ms": record.get("sla_ms"),
                },
            )
            self._append_event_unlocked(
                task_id=task_id,
                event_type="queued",
                from_status="routed",
                to_status=queued_status,
                message="task queued for worker consumption",
                metadata={"queue": record.get("queue")},
            )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                persisted = task_state_store.get_task(task_id)
                if persisted is None:
                    return None
                self._tasks[task_id] = persisted
                return dict(persisted)
            return dict(record)

    @staticmethod
    def _event_matches(
        event: dict[str, Any],
        *,
        event_type: str | None,
        start_ts: str | None,
        end_ts: str | None,
    ) -> bool:
        if event_type and str(event.get("event_type")) != event_type:
            return False

        event_ts = str(event.get("ts") or "")
        if start_ts and event_ts < start_ts:
            return False
        if end_ts and event_ts > end_ts:
            return False

        return True

    def list_events(
        self,
        task_id: str,
        *,
        event_type: str | None = None,
        start_ts: str | None = None,
        end_ts: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self._lock:
            task_exists = task_id in self._tasks
            memory_events = [dict(item) for item in self._events.get(task_id, [])]

        persisted_events = task_event_store.list_events(
            task_id,
            event_type=event_type,
            start_ts=start_ts,
            end_ts=end_ts,
            limit=limit,
            offset=offset,
        )
        if persisted_events:
            return persisted_events
        if not task_exists:
            return []

        filtered = [
            item
            for item in memory_events
            if self._event_matches(
                item,
                event_type=event_type,
                start_ts=start_ts,
                end_ts=end_ts,
            )
        ]
        return filtered[offset : offset + limit]

    def count_events(
        self,
        task_id: str,
        *,
        event_type: str | None = None,
        start_ts: str | None = None,
        end_ts: str | None = None,
    ) -> int:
        persisted_count = task_event_store.count_events(
            task_id,
            event_type=event_type,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        if persisted_count > 0:
            return persisted_count

        with self._lock:
            memory_events = [dict(item) for item in self._events.get(task_id, [])]

        return len(
            [
                item
                for item in memory_events
                if self._event_matches(
                    item,
                    event_type=event_type,
                    start_ts=start_ts,
                    end_ts=end_ts,
                )
            ]
        )

    def transition_task(
        self,
        task_id: str,
        *,
        new_status: str,
        event_type: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return None

            previous_status = str(record.get("status", "queued"))
            if previous_status == new_status:
                logger.warning(
                    "reject noop transition: task_id=%s from=%s to=%s",
                    task_id,
                    previous_status,
                    new_status,
                )
                return None

            allowed_next = ALLOWED_TASK_TRANSITIONS.get(previous_status)
            if allowed_next is None or new_status not in allowed_next:
                logger.warning(
                    "reject invalid transition: task_id=%s from=%s to=%s",
                    task_id,
                    previous_status,
                    new_status,
                )
                return None

            record["status"] = new_status
            record["updated_at"] = now
            if new_status == "running":
                record["attempts"] = int(record.get("attempts", 0)) + 1
                record["started_at"] = now
            if new_status in FINAL_STATUSES:
                record["finished_at"] = now
            if result is not None:
                record["result"] = result
            if error is not None:
                record["error"] = error

            try:
                task_state_store.save_task(record)
            except Exception as exc:  # pragma: no cover - persistence fallback path
                logger.warning("task state persistence failed on transition: %s", exc)

            self._append_event_unlocked(
                task_id=task_id,
                event_type=event_type,
                from_status=previous_status,
                to_status=new_status,
                message=message,
                metadata=metadata,
            )
            return dict(record)

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()
            self._events.clear()
        task_event_store.clear()
        task_state_store.clear()


task_registry = InMemoryTaskRegistry()
