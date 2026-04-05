"""Task worker service for scaffold-stage queue consumption."""

from __future__ import annotations

import math
from typing import Any

from app.core.config import settings
from app.core.errors import HelioraError
from app.services.task_queue import task_queue_service
from app.services.task_registry import task_registry


FINAL_OR_CANCELED_STATUSES = {"completed", "failed", "canceled"}


class InMemoryTaskWorker:
    """Consume queued tasks and advance status lifecycle."""

    @staticmethod
    def _compute_retry_delay_seconds(attempts: int) -> float:
        """Compute exponential backoff delay for retryable failures."""
        if attempts < 1:
            return 0.0

        base = max(settings.task_retry_base_delay_seconds, 0.0)
        factor = max(settings.task_retry_backoff_factor, 1.0)
        max_delay = max(settings.task_retry_max_delay_seconds, 0.0)

        delay = base * math.pow(factor, attempts - 1)
        return max(0.0, min(delay, max_delay))

    def consume_next(self, queue: str | None = None, force_fail: bool = False) -> dict[str, Any]:
        envelope = task_queue_service.consume_one(queue=queue)
        if envelope is None:
            return {
                "consumed": False,
                "task": None,
                "events": [],
            }

        task_id = str(envelope.task_id)
        queued_task = task_registry.get_task(task_id)
        if queued_task is None:
            return {
                "consumed": False,
                "task": None,
                "events": [],
            }

        current_status = str(queued_task.get("status", "queued"))
        if current_status in FINAL_OR_CANCELED_STATUSES:
            return {
                "consumed": True,
                "skipped": True,
                "task": queued_task,
                "events": task_registry.list_events(task_id),
            }

        running_task = task_registry.transition_task(
            task_id,
            new_status="running",
            event_type="running",
            message="worker picked task",
            metadata={"queue": envelope.queue},
        )
        if running_task is None:
            raise HelioraError(
                code="TASK_TRANSITION_INVALID",
                status_code=409,
                message=f"invalid task transition: {current_status} -> running",
                details={"task_id": task_id, "from": current_status, "to": "running"},
            )

        payload = envelope.payload or {}
        should_fail = bool(force_fail or payload.get("force_fail") is True)

        if should_fail:
            attempts = int(running_task.get("attempts", 1))
            max_attempts = int(settings.task_retry_max_attempts)
            retry_delay_seconds = 0.0
            if attempts < max_attempts:
                retry_delay_seconds = self._compute_retry_delay_seconds(attempts)

            requeue_meta = task_queue_service.requeue_or_dead_letter(
                envelope,
                attempts=attempts,
                retry_delay_seconds=retry_delay_seconds,
                error_message="forced failure for test path",
            )

            if requeue_meta.get("action") == "requeued":
                retrying_task = task_registry.transition_task(
                    task_id,
                    new_status="retrying",
                    event_type="retrying",
                    message="task scheduled for retry",
                    metadata={
                        "reason": "forced failure for test path",
                        **requeue_meta,
                    },
                )
                if retrying_task is None:
                    raise HelioraError(
                        code="TASK_TRANSITION_INVALID",
                        status_code=409,
                        message="invalid task transition: running -> retrying",
                        details={"task_id": task_id, "from": "running", "to": "retrying"},
                    )
                return {
                    "consumed": True,
                    "task": retrying_task,
                    "events": task_registry.list_events(task_id),
                }

            failed_task = task_registry.transition_task(
                task_id,
                new_status="failed",
                event_type="failed",
                message="task execution failed",
                metadata={
                    "reason": "forced failure for test path",
                    **requeue_meta,
                },
                error={
                    "code": "TASK_EXECUTION_FAILED",
                    "message": "forced failure for test path",
                },
            )
            if failed_task is None:
                raise HelioraError(
                    code="TASK_TRANSITION_INVALID",
                    status_code=409,
                    message="invalid task transition: running -> failed",
                    details={"task_id": task_id, "from": "running", "to": "failed"},
                )
            return {
                "consumed": True,
                "task": failed_task,
                "events": task_registry.list_events(task_id),
            }

        completed_task = task_registry.transition_task(
            task_id,
            new_status="completed",
            event_type="completed",
            message="task execution completed",
            result={
                "summary": f"task {task_id} completed by in-memory worker",
                "queue": envelope.queue,
            },
        )
        if completed_task is None:
            raise HelioraError(
                code="TASK_TRANSITION_INVALID",
                status_code=409,
                message="invalid task transition: running -> completed",
                details={"task_id": task_id, "from": "running", "to": "completed"},
            )
        return {
            "consumed": True,
            "task": completed_task,
            "events": task_registry.list_events(task_id),
        }


in_memory_task_worker = InMemoryTaskWorker()
