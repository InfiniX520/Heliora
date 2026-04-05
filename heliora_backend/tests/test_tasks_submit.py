"""Task submission endpoint tests."""

from collections.abc import Generator
from typing import Never

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.services.task_event_store import task_event_store
from app.services.task_queue import task_queue_service
from app.services.idempotency import idempotency_store
from app.services.task_registry import task_registry
from app.services.task_state_store import task_state_store


client = TestClient(app)


def _payload(priority: str = "P2") -> dict:
    return {
        "task_type": "course.plan.generate",
        "priority": priority,
        "required_capabilities": ["planner"],
        "payload": {"topic": "linear algebra"},
    }


@pytest.fixture(autouse=True)
def reset_idempotency_store() -> Generator[None, None, None]:
    idempotency_store.clear()
    task_registry.clear()
    task_queue_service._memory._queues.clear()  # type: ignore[attr-defined]
    yield
    idempotency_store.clear()
    task_registry.clear()
    task_queue_service._memory._queues.clear()  # type: ignore[attr-defined]


def test_submit_task_requires_idempotency_key() -> None:
    response = client.post("/api/v1/tasks/submit", json=_payload())

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ARGUMENT"


def test_submit_task_returns_accepted() -> None:
    response = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-ok-1"},
        json=_payload(priority="P2"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["code"] == "ACCEPTED"
    assert body["data"]["queue"] == "normal.queue"
    assert body["data"]["status"] == "queued"
    assert body["data"]["task_id"].startswith("task_")


def test_submit_task_replay_returns_same_task() -> None:
    first = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-replay-1"},
        json=_payload(priority="P1"),
    )
    second = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-replay-1"},
        json=_payload(priority="P1"),
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["message"] == "task accepted (idempotent replay)"
    assert first.json()["data"]["task_id"] == second.json()["data"]["task_id"]


def test_submit_task_reuse_key_with_different_payload_returns_conflict() -> None:
    first = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-conflict-1"},
        json=_payload(priority="P2"),
    )
    second = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-conflict-1"},
        json=_payload(priority="P0"),
    )

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"


def test_get_task_status_after_submit() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-query-1"},
        json=_payload(priority="P3"),
    )
    task_id = submit.json()["data"]["task_id"]

    query = client.get(f"/api/v1/tasks/{task_id}")

    assert submit.status_code == 202
    assert query.status_code == 200
    assert query.json()["data"]["task_id"] == task_id
    assert query.json()["data"]["status"] == "queued"


def test_get_task_status_not_found() -> None:
    response = client.get("/api/v1/tasks/task_missing")

    assert response.status_code == 404
    assert response.json()["code"] == "TASK_NOT_FOUND"


def test_get_task_events_after_submit() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-events-1"},
        json=_payload(priority="P2"),
    )
    task_id = submit.json()["data"]["task_id"]

    events_response = client.get(f"/api/v1/tasks/{task_id}/events")

    assert events_response.status_code == 200
    events = events_response.json()["data"]["events"]
    event_types = [event["event_type"] for event in events]
    assert event_types[:3] == ["created", "routed", "queued"]


def test_get_task_events_supports_pagination() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-events-page-1"},
        json=_payload(priority="P2"),
    )
    task_id = submit.json()["data"]["task_id"]

    consume = client.post(
        "/api/v1/tasks/consume-next",
        json={"queue": "normal.queue"},
    )
    events_response = client.get(f"/api/v1/tasks/{task_id}/events?limit=2&offset=1")

    assert consume.status_code == 200
    assert events_response.status_code == 200
    data = events_response.json()["data"]
    assert data["limit"] == 2
    assert data["offset"] == 1
    assert data["total"] >= 5
    assert len(data["events"]) == 2
    assert data["has_more"] is True


def test_get_task_events_supports_event_type_filter() -> None:
    payload = _payload(priority="P2")
    payload["payload"]["force_fail"] = True
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-events-filter-1"},
        json=payload,
    )
    task_id = submit.json()["data"]["task_id"]

    first_consume = client.post(
        "/api/v1/tasks/consume-next",
        json={"queue": "normal.queue"},
    )
    events_response = client.get(f"/api/v1/tasks/{task_id}/events?event_type=retrying")

    assert first_consume.status_code == 200
    assert events_response.status_code == 200
    data = events_response.json()["data"]
    assert data["event_type"] == "retrying"
    assert data["total"] == 1
    assert len(data["events"]) == 1
    assert data["events"][0]["event_type"] == "retrying"


def test_get_task_events_rejects_invalid_start_ts() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-events-invalid-ts-1"},
        json=_payload(priority="P2"),
    )
    task_id = submit.json()["data"]["task_id"]

    events_response = client.get(f"/api/v1/tasks/{task_id}/events?start_ts=not-a-time")

    assert submit.status_code == 202
    assert events_response.status_code == 400
    assert events_response.json()["code"] == "INVALID_ARGUMENT"


def test_get_task_events_rejects_reversed_time_window() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-events-invalid-range-1"},
        json=_payload(priority="P2"),
    )
    task_id = submit.json()["data"]["task_id"]

    events_response = client.get(
        f"/api/v1/tasks/{task_id}/events"
        "?start_ts=2026-04-02T00:00:00Z&end_ts=2026-04-01T00:00:00Z"
    )

    assert submit.status_code == 202
    assert events_response.status_code == 400
    assert events_response.json()["code"] == "INVALID_ARGUMENT"


def test_consume_next_task_completes_and_updates_status() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-consume-1"},
        json=_payload(priority="P2"),
    )
    task_id = submit.json()["data"]["task_id"]

    consume = client.post(
        "/api/v1/tasks/consume-next",
        json={"queue": "normal.queue"},
    )
    status_response = client.get(f"/api/v1/tasks/{task_id}")

    assert consume.status_code == 200
    consume_body = consume.json()
    assert consume_body["code"] == "OK"
    assert consume_body["message"] == "task execution completed"
    assert consume_body["data"]["task"]["task_id"] == task_id
    assert consume_body["data"]["task"]["status"] == "completed"
    assert status_response.json()["data"]["status"] == "completed"
    assert status_response.json()["data"]["attempts"] == 1


def test_consume_next_task_force_fail_enters_retrying() -> None:
    payload = _payload(priority="P2")
    payload["payload"]["force_fail"] = True
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-consume-fail-1"},
        json=payload,
    )
    task_id = submit.json()["data"]["task_id"]

    consume = client.post(
        "/api/v1/tasks/consume-next",
        json={"queue": "normal.queue"},
    )
    events_response = client.get(f"/api/v1/tasks/{task_id}/events")

    assert consume.status_code == 200
    consume_body = consume.json()
    assert consume_body["code"] == "ACCEPTED"
    assert consume_body["message"] == "task scheduled for retry"
    assert consume_body["data"]["task"]["status"] == "retrying"
    event_types = [event["event_type"] for event in events_response.json()["data"]["events"]]
    assert event_types[-2:] == ["running", "retrying"]


def test_consume_force_fail_requeues_before_max_attempts() -> None:
    payload = _payload(priority="P2")
    payload["payload"]["force_fail"] = True
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-requeue-1"},
        json=payload,
    )
    task_id = submit.json()["data"]["task_id"]

    first_consume = client.post(
        "/api/v1/tasks/consume-next",
        json={"queue": "normal.queue"},
    )
    events = client.get(f"/api/v1/tasks/{task_id}/events").json()["data"]["events"]
    retrying_event = [evt for evt in events if evt["event_type"] == "retrying"][-1]

    assert first_consume.status_code == 200
    assert first_consume.json()["code"] == "ACCEPTED"
    assert retrying_event["metadata"]["action"] == "requeued"
    assert retrying_event["metadata"]["backend"] == "memory"
    assert retrying_event["metadata"]["attempts"] == 1
    assert retrying_event["metadata"]["retry_delay_seconds"] > 0
    assert retrying_event["metadata"]["next_retry_at"] > 0


def test_consume_force_fail_dead_letters_on_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "task_retry_base_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "task_retry_max_delay_seconds", 0.0)

    payload = _payload(priority="P2")
    payload["payload"]["force_fail"] = True
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-dead-1"},
        json=payload,
    )
    task_id = submit.json()["data"]["task_id"]

    first_consume = client.post(
        "/api/v1/tasks/consume-next",
        json={"queue": "normal.queue"},
    )
    second_consume = client.post(
        "/api/v1/tasks/consume-next",
        json={"queue": "normal.queue"},
    )
    events = client.get(f"/api/v1/tasks/{task_id}/events").json()["data"]["events"]
    failed_event = [evt for evt in events if evt["event_type"] == "failed"][-1]

    assert first_consume.status_code == 200
    assert second_consume.status_code == 200
    assert first_consume.json()["code"] == "ACCEPTED"
    assert first_consume.json()["data"]["task"]["status"] == "retrying"
    assert second_consume.json()["code"] == "OK"
    assert second_consume.json()["data"]["task"]["status"] == "failed"
    assert failed_event["metadata"]["action"] == "dead_lettered"
    assert failed_event["metadata"]["backend"] == "memory"
    assert failed_event["metadata"]["attempts"] == 2
    assert failed_event["metadata"]["queue"] == "normal.queue.dead"
    assert failed_event["metadata"]["retry_delay_seconds"] == pytest.approx(0.0)


def test_submit_task_fallbacks_on_recoverable_rabbitmq_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "task_queue_backend", "rabbitmq")
    monkeypatch.setattr(settings, "task_queue_fail_open", True)

    def _raise_connection_error(*args: object, **kwargs: object) -> Never:  # noqa: ARG001
        raise ConnectionError("rabbitmq connection lost")

    monkeypatch.setattr(task_queue_service._rabbit, "publish", _raise_connection_error)

    response = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-rmq-fallback-1"},
        json=_payload(priority="P2"),
    )

    assert response.status_code == 202
    assert response.json()["code"] == "ACCEPTED"
    assert len(task_queue_service._memory._queues.get("normal.queue", [])) == 1  # type: ignore[attr-defined]


def test_submit_task_does_not_fallback_on_non_recoverable_rabbitmq_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "task_queue_backend", "rabbitmq")
    monkeypatch.setattr(settings, "task_queue_fail_open", True)

    def _raise_value_error(*args: object, **kwargs: object) -> Never:  # noqa: ARG001
        raise ValueError("payload serialization bug")

    monkeypatch.setattr(task_queue_service._rabbit, "publish", _raise_value_error)

    response = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-rmq-no-fallback-1"},
        json=_payload(priority="P2"),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "TASK_QUEUE_UNAVAILABLE"


def test_task_events_are_persisted() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-events-persist-1"},
        json=_payload(priority="P2"),
    )
    task_id = submit.json()["data"]["task_id"]

    consume = client.post(
        "/api/v1/tasks/consume-next",
        json={"queue": "normal.queue"},
    )
    persisted_events = task_event_store.list_events(task_id)

    assert consume.status_code == 200
    assert len(persisted_events) >= 5
    assert persisted_events[0]["event_type"] == "created"
    assert persisted_events[-1]["event_type"] in {"completed", "failed"}


def test_consume_next_task_noop_when_empty_queue() -> None:
    consume = client.post(
        "/api/v1/tasks/consume-next",
        json={"queue": "normal.queue"},
    )

    assert consume.status_code == 200
    body = consume.json()
    assert body["code"] == "NOOP"
    assert body["data"]["consumed"] is False


def test_get_task_events_not_found() -> None:
    response = client.get("/api/v1/tasks/task_missing/events")

    assert response.status_code == 404
    assert response.json()["code"] == "TASK_NOT_FOUND"


def test_submit_memory_task_routes_to_memory_queue() -> None:
    payload = {
        "task_type": "memory.feedback",
        "priority": "P2",
        "required_capabilities": ["memory"],
        "payload": {"memory_id": "mem_x1"},
    }

    response = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-memory-queue-1"},
        json=payload,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["data"]["queue"] == "memory.queue"
    assert body["data"]["sla_ms"] == 5000


def test_cancel_task_sets_status_to_canceled() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-cancel-1"},
        json=_payload(priority="P2"),
    )
    task_id = submit.json()["data"]["task_id"]

    cancel = client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        json={"reason": "manual stop"},
    )
    status_response = client.get(f"/api/v1/tasks/{task_id}")

    assert cancel.status_code == 200
    assert cancel.json()["data"]["canceled"] is True
    assert status_response.json()["data"]["status"] == "canceled"


def test_cancel_task_rejects_finished_task() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-cancel-finished-1"},
        json=_payload(priority="P2"),
    )
    task_id = submit.json()["data"]["task_id"]

    consume = client.post(
        "/api/v1/tasks/consume-next",
        json={"queue": "normal.queue"},
    )
    cancel = client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        json={"reason": "too late"},
    )

    assert consume.status_code == 200
    assert cancel.status_code == 409
    assert cancel.json()["code"] == "TASK_ALREADY_FINISHED"


def test_consume_skips_canceled_task() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-cancel-skip-1"},
        json=_payload(priority="P2"),
    )
    task_id = submit.json()["data"]["task_id"]

    cancel = client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        json={"reason": "skip execution"},
    )
    consume = client.post(
        "/api/v1/tasks/consume-next",
        json={"queue": "normal.queue"},
    )

    assert cancel.status_code == 200
    assert consume.status_code == 200
    assert consume.json()["code"] == "NOOP"
    assert consume.json()["data"]["task"]["status"] == "canceled"


def test_registry_rejects_invalid_transition() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-transition-guard-1"},
        json=_payload(priority="P2"),
    )
    task_id = submit.json()["data"]["task_id"]

    invalid = task_registry.transition_task(
        task_id,
        new_status="completed",
        event_type="completed",
        message="invalid jump",
    )

    assert submit.status_code == 202
    assert invalid is None


def test_get_task_events_reads_persistent_store_when_task_missing() -> None:
    task_state_store.save_task(
        {
            "task_id": "task_persist_only_1",
            "task_type": "persist_only_probe",
            "priority": "P2",
            "required_capabilities": ["planner"],
            "payload": {"source": "test"},
            "queue": "normal.queue",
            "sla_ms": 15000,
            "status": "completed",
            "attempts": 1,
            "created_at": "2026-04-01T00:00:00+00:00",
            "updated_at": "2026-04-01T00:00:00+00:00",
        }
    )

    task_event_store.save_event(
        {
            "event_id": "evt_persist_only_1",
            "task_id": "task_persist_only_1",
            "event_type": "completed",
            "from_status": "running",
            "to_status": "completed",
            "message": "persisted only event",
            "metadata": {"source": "test"},
            "ts": "2026-04-01T00:00:00+00:00",
        }
    )

    task_registry._tasks.pop("task_persist_only_1", None)  # type: ignore[attr-defined]
    task_registry._events.pop("task_persist_only_1", None)  # type: ignore[attr-defined]

    response = client.get("/api/v1/tasks/task_persist_only_1/events")

    assert response.status_code == 200
    assert response.json()["data"]["source"] in {"registry", "persistent_store"}
    assert response.json()["data"]["total"] == 1
    assert response.json()["data"]["events"][0]["event_id"] == "evt_persist_only_1"


def test_get_task_status_reads_persistent_registry_when_memory_missing() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-task-registry-persist-1"},
        json=_payload(priority="P2"),
    )
    task_id = submit.json()["data"]["task_id"]

    task_registry._tasks.clear()  # type: ignore[attr-defined]
    response = client.get(f"/api/v1/tasks/{task_id}")

    assert submit.status_code == 202
    assert response.status_code == 200
    assert response.json()["data"]["task_id"] == task_id
    assert response.json()["data"]["status"] == "queued"
