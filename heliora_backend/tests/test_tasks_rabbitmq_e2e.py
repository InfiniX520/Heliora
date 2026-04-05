"""RabbitMQ end-to-end tests for task queue behavior."""

from collections.abc import Generator
import os
import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.idempotency import idempotency_store
from app.services.task_event_store import task_event_store
from app.services.task_queue import RabbitMqQueueBackend, task_queue_service
from app.services.task_registry import task_registry
from app.services.task_state_store import task_state_store


client = TestClient(app)


def _rabbitmq_e2e_required() -> bool:
    raw = os.getenv("RABBITMQ_E2E_REQUIRED", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _rabbitmq_available() -> bool:
    try:
        import pika

        params = pika.URLParameters(settings.rabbitmq_url)
        connection = pika.BlockingConnection(params)
        connection.close()
        return True
    except Exception:
        return False


def _wait_for_rabbitmq(timeout_seconds: float = 30.0, interval_seconds: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _rabbitmq_available():
            return True
        time.sleep(interval_seconds)
    return _rabbitmq_available()


def _purge_rabbit_queues() -> None:
    import pika

    queue_names = (
        "realtime.queue",
        "normal.queue",
        "memory.queue",
        "batch.queue",
        "realtime.queue.retry",
        "normal.queue.retry",
        "memory.queue.retry",
        "batch.queue.retry",
        "realtime.queue.dead",
        "normal.queue.dead",
        "memory.queue.dead",
        "batch.queue.dead",
    )

    params = pika.URLParameters(settings.rabbitmq_url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    try:
        for queue_name in queue_names:
            channel.queue_declare(queue=queue_name, durable=True)
            channel.queue_purge(queue=queue_name)
    finally:
        connection.close()


@pytest.fixture(scope="module")
def require_rabbitmq() -> None:
    if _wait_for_rabbitmq():
        return

    message = "RabbitMQ is not available for E2E tests"
    if _rabbitmq_e2e_required():
        pytest.fail(f"{message} (RABBITMQ_E2E_REQUIRED=true)")
    pytest.skip(message)


@pytest.fixture(autouse=True)
def reset_state(monkeypatch: pytest.MonkeyPatch, require_rabbitmq: None) -> Generator[None, None, None]:
    idempotency_store.clear()
    task_registry.clear()
    _purge_rabbit_queues()

    monkeypatch.setattr(settings, "task_queue_backend", "rabbitmq")
    monkeypatch.setattr(settings, "task_queue_fail_open", False)
    monkeypatch.setattr(settings, "task_retry_max_attempts", 2)
    monkeypatch.setattr(settings, "task_retry_base_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "task_retry_max_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "task_retry_backoff_factor", 2.0)
    task_queue_service._rabbit = RabbitMqQueueBackend(settings.rabbitmq_url)

    yield

    idempotency_store.clear()
    task_registry.clear()
    _purge_rabbit_queues()


def test_rabbitmq_retry_and_dead_letter_e2e() -> None:
    submit = client.post(
        "/api/v1/tasks/submit",
        headers={"Idempotency-Key": "idem-rabbit-e2e-1"},
        json={
            "task_type": "retry_probe",
            "priority": "P2",
            "required_capabilities": ["worker"],
            "payload": {"force_fail": True},
        },
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

    retrying_events = client.get(f"/api/v1/tasks/{task_id}/events?event_type=retrying").json()["data"]
    failed_events = client.get(f"/api/v1/tasks/{task_id}/events?event_type=failed").json()["data"]

    assert submit.status_code == 202
    assert first_consume.status_code == 200
    assert second_consume.status_code == 200

    assert first_consume.json()["code"] == "ACCEPTED"
    assert first_consume.json()["data"]["task"]["status"] == "retrying"
    assert second_consume.json()["code"] == "OK"
    assert second_consume.json()["data"]["task"]["status"] == "failed"

    assert retrying_events["total"] == 1
    retrying_event = retrying_events["events"][0]
    assert retrying_event["metadata"]["action"] == "requeued"
    assert retrying_event["metadata"]["backend"] == "rabbitmq"

    assert failed_events["total"] == 1
    failed_event = failed_events["events"][0]
    assert failed_event["metadata"]["action"] == "dead_lettered"
    assert failed_event["metadata"]["backend"] == "rabbitmq"
    assert failed_event["metadata"]["queue"] == "normal.queue.dead"

    persisted_task = task_state_store.get_task(task_id)
    persisted_retrying_total = task_event_store.count_events(task_id, event_type="retrying")
    persisted_failed_total = task_event_store.count_events(task_id, event_type="failed")

    assert persisted_task is not None
    assert persisted_task["status"] == "failed"
    assert persisted_retrying_total == 1
    assert persisted_failed_total == 1
