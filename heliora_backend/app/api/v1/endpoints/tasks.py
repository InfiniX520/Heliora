"""Task endpoints."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import enforce_security_mode, require_idempotency_key
from app.core.errors import HelioraError
from app.core.response import success_response
from app.schemas.tasks import TaskCancelRequest, TaskConsumeRequest, TaskSubmitRequest
from app.services.idempotency import idempotency_store
from app.services.task_queue import QueueEnvelope, task_queue_service
from app.services.task_routing import select_queue_and_sla
from app.services.task_registry import task_registry
from app.services.task_worker import in_memory_task_worker


router = APIRouter(tags=["tasks"])
FINAL_TASK_STATUSES = {"completed", "failed", "canceled"}


def _normalize_filter_ts(raw_value: str | None, field_name: str) -> str | None:
    if raw_value is None:
        return None

    value = raw_value.strip()
    if not value:
        raise HelioraError(
            code="INVALID_ARGUMENT",
            status_code=400,
            message=f"{field_name} must not be blank",
        )

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HelioraError(
            code="INVALID_ARGUMENT",
            status_code=400,
            message=f"{field_name} must be a valid ISO-8601 datetime",
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    return parsed.isoformat()


@router.post("/tasks/submit", status_code=status.HTTP_202_ACCEPTED)
async def submit_task(
    request: Request,
    body: TaskSubmitRequest,
    idempotency_key: str = Depends(require_idempotency_key),
) -> dict:
    """Submit placeholder task into queue model for scaffold stage."""
    enforce_security_mode(request)

    payload = body.model_dump(mode="json")
    fingerprint = idempotency_store.build_fingerprint(payload)
    replay_data = idempotency_store.get_replay(idempotency_key, fingerprint)
    if replay_data is not None:
        return success_response(
            request,
            data=replay_data,
            code="ACCEPTED",
            message="task accepted (idempotent replay)",
        )

    queue, sla_ms = select_queue_and_sla(
        body.priority,
        body.task_type,
        body.required_capabilities,
    )
    task_id = f"task_{uuid4().hex[:10]}"
    payload_data = dict(body.payload)
    data: dict[str, Any] = {
        "task_id": task_id,
        "task_type": body.task_type,
        "priority": body.priority,
        "required_capabilities": body.required_capabilities,
        "payload": payload_data,
        "queue": queue,
        "sla_ms": sla_ms,
        "status": "queued",
    }
    task_queue_service.publish(
        QueueEnvelope(
            task_id=task_id,
            queue=queue,
            payload=payload_data,
        )
    )
    task_registry.save_task(data)
    idempotency_store.save(idempotency_key, fingerprint, data)
    return success_response(request, data=data, code="ACCEPTED", message="task accepted")


@router.get("/tasks/{task_id}")
async def get_task_status(request: Request, task_id: str) -> dict:
    """Get task status from scaffold task registry."""
    task = task_registry.get_task(task_id)
    if task is None:
        raise HelioraError(
            code="TASK_NOT_FOUND",
            status_code=404,
            message=f"task not found: {task_id}",
        )

    return success_response(request, data=task)


@router.get("/tasks/{task_id}/events")
async def get_task_events(
    request: Request,
    task_id: str,
    event_type: str | None = Query(default=None),
    start_ts: str | None = Query(default=None),
    end_ts: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Get task lifecycle events for audit and troubleshooting."""
    normalized_start_ts = _normalize_filter_ts(start_ts, "start_ts")
    normalized_end_ts = _normalize_filter_ts(end_ts, "end_ts")
    if (
        normalized_start_ts is not None
        and normalized_end_ts is not None
        and normalized_start_ts > normalized_end_ts
    ):
        raise HelioraError(
            code="INVALID_ARGUMENT",
            status_code=400,
            message="start_ts must be earlier than or equal to end_ts",
        )

    task = task_registry.get_task(task_id)
    total = task_registry.count_events(
        task_id,
        event_type=event_type,
        start_ts=normalized_start_ts,
        end_ts=normalized_end_ts,
    )

    if task is None and total == 0:
        raise HelioraError(
            code="TASK_NOT_FOUND",
            status_code=404,
            message=f"task not found: {task_id}",
        )

    events = task_registry.list_events(
        task_id,
        event_type=event_type,
        start_ts=normalized_start_ts,
        end_ts=normalized_end_ts,
        limit=limit,
        offset=offset,
    )

    source = "persistent_store" if task is None else "registry"
    has_more = offset + len(events) < total
    return success_response(
        request,
        data={
            "task_id": task_id,
            "events": events,
            "event_type": event_type,
            "start_ts": normalized_start_ts,
            "end_ts": normalized_end_ts,
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": has_more,
            "source": source,
        },
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(request: Request, task_id: str, body: TaskCancelRequest) -> dict:
    """Cancel one queued/running task."""
    enforce_security_mode(request)

    task = task_registry.get_task(task_id)
    if task is None:
        raise HelioraError(
            code="TASK_NOT_FOUND",
            status_code=404,
            message=f"task not found: {task_id}",
        )

    current_status = str(task.get("status", "queued"))
    if current_status in FINAL_TASK_STATUSES:
        raise HelioraError(
            code="TASK_ALREADY_FINISHED",
            status_code=409,
            message=f"task cannot be canceled from status={current_status}",
        )

    canceled_task = task_registry.transition_task(
        task_id,
        new_status="canceled",
        event_type="canceled",
        message="task canceled",
        metadata={"reason": body.reason or "user_request"},
    )
    if canceled_task is None:
        raise HelioraError(
            code="TASK_CANCEL_REJECTED",
            status_code=409,
            message=f"task cancel rejected: {task_id}",
        )

    return success_response(
        request,
        data={
            "task_id": task_id,
            "canceled": True,
            "status": "canceled",
        },
    )


@router.post("/tasks/consume-next")
async def consume_next_task(request: Request, body: TaskConsumeRequest) -> dict:
    """Consume one queued task and push status to completed/failed."""
    enforce_security_mode(request)

    consume_result = in_memory_task_worker.consume_next(
        queue=body.queue,
        force_fail=body.force_fail,
    )
    if not consume_result["consumed"]:
        return success_response(
            request,
            code="NOOP",
            message="no queued task available",
            data=consume_result,
        )

    if consume_result.get("skipped"):
        return success_response(
            request,
            code="NOOP",
            message="task skipped because it is already in a terminal status",
            data=consume_result,
        )

    task = consume_result["task"]
    if task["status"] == "failed":
        return success_response(
            request,
            code="OK",
            message="task execution failed",
            data=consume_result,
        )

    if task["status"] == "retrying":
        return success_response(
            request,
            code="ACCEPTED",
            message="task scheduled for retry",
            data=consume_result,
        )

    return success_response(
        request,
        code="OK",
        message="task execution completed",
        data=consume_result,
    )
