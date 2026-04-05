"""Task queue backend abstraction with memory and RabbitMQ implementations."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast

from app.core.config import settings
from app.core.errors import HelioraError


logger = logging.getLogger(__name__)


class _DeliveryFrame(Protocol):
    delivery_tag: int


class _RabbitMqChannel(Protocol):
    def queue_declare(
        self,
        *,
        queue: str,
        durable: bool = True,
        arguments: dict[str, object] | None = None,
    ) -> object: ...

    def basic_publish(
        self,
        *,
        exchange: str,
        routing_key: str,
        body: bytes,
        properties: object | None = None,
    ) -> bool | None: ...

    def basic_get(
        self,
        *,
        queue: str,
        auto_ack: bool = False,
    ) -> tuple[_DeliveryFrame | None, object | None, bytes]: ...

    def basic_ack(self, delivery_tag: int) -> None: ...


class _RabbitMqConnection(Protocol):
    def channel(self) -> _RabbitMqChannel: ...

    def close(self) -> None: ...


QueueOpResult = TypeVar("QueueOpResult")


@dataclass
class QueueEnvelope:
    """Queue envelope transported by backend queues."""

    task_id: str
    queue: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "queue": self.queue,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "QueueEnvelope":
        return cls(
            task_id=str(value["task_id"]),
            queue=str(value["queue"]),
            payload=dict(value.get("payload") or {}),
        )


class BaseTaskQueueBackend:
    """Abstract queue backend contract."""

    def publish(self, envelope: QueueEnvelope) -> None:
        raise NotImplementedError

    def consume_one(self, queue: str | None = None) -> QueueEnvelope | None:
        raise NotImplementedError

    def requeue_or_dead_letter(
        self,
        envelope: QueueEnvelope,
        *,
        attempts: int,
        max_attempts: int,
        retry_delay_seconds: float,
        error_message: str,
    ) -> dict[str, Any]:
        raise NotImplementedError


class InMemoryQueueBackend(BaseTaskQueueBackend):
    """Simple process-local queue backend."""

    def __init__(self) -> None:
        self._queues: dict[str, list[dict[str, Any]]] = {}

    def publish(self, envelope: QueueEnvelope) -> None:
        self._queues.setdefault(envelope.queue, []).append(envelope.to_dict())

    def consume_one(self, queue: str | None = None) -> QueueEnvelope | None:
        now_ts = time.time()

        def _pop_available(queue_name: str) -> QueueEnvelope | None:
            queue_items = self._queues.get(queue_name, [])
            if not queue_items:
                return None
            for idx, candidate in enumerate(queue_items):
                not_before_ts = float(candidate.get("_not_before_ts") or 0.0)
                if not_before_ts > now_ts:
                    continue
                return QueueEnvelope.from_dict(queue_items.pop(idx))
            return None

        if queue is not None:
            return _pop_available(queue)

        for queue_name in ("realtime.queue", "normal.queue", "memory.queue", "batch.queue"):
            envelope = _pop_available(queue_name)
            if envelope is not None:
                return envelope

        for queue_name in self._queues:
            envelope = _pop_available(queue_name)
            if envelope is not None:
                return envelope

        return None

    def requeue_or_dead_letter(
        self,
        envelope: QueueEnvelope,
        *,
        attempts: int,
        max_attempts: int,
        retry_delay_seconds: float,
        error_message: str,
    ) -> dict[str, Any]:
        if attempts < max_attempts:
            next_retry_at = time.time() + max(retry_delay_seconds, 0.0)
            queued = {
                **envelope.to_dict(),
                "_not_before_ts": next_retry_at,
            }
            self._queues.setdefault(envelope.queue, []).append(queued)
            return {
                "action": "requeued",
                "backend": "memory",
                "queue": envelope.queue,
                "attempts": attempts,
                "max_attempts": max_attempts,
                "retry_delay_seconds": float(retry_delay_seconds),
                "next_retry_at": next_retry_at,
            }

        dead_letter_queue = f"{envelope.queue}.dead"
        self._queues.setdefault(dead_letter_queue, []).append(
            {
                **envelope.to_dict(),
                "dead_reason": error_message,
            }
        )
        return {
            "action": "dead_lettered",
            "backend": "memory",
            "queue": dead_letter_queue,
            "attempts": attempts,
            "max_attempts": max_attempts,
            "retry_delay_seconds": 0.0,
        }


class RabbitMqQueueBackend(BaseTaskQueueBackend):
    """RabbitMQ backend using pika (imported lazily)."""

    def __init__(self, amqp_url: str) -> None:
        self._amqp_url = amqp_url

    def _with_channel(self, fn: Callable[[_RabbitMqChannel], QueueOpResult]) -> QueueOpResult:
        try:
            import pika
        except Exception as exc:  # pragma: no cover - depends on runtime package state
            raise RuntimeError("pika is required for rabbitmq backend") from exc

        params = pika.URLParameters(self._amqp_url)
        connection = cast(_RabbitMqConnection, pika.BlockingConnection(params))
        channel = connection.channel()
        try:
            return fn(channel)
        finally:
            connection.close()

    def _declare_queue(self, channel: _RabbitMqChannel, queue: str) -> None:
        channel.queue_declare(queue=queue, durable=True)

    def publish(self, envelope: QueueEnvelope) -> None:
        body = json.dumps(envelope.to_dict(), ensure_ascii=True).encode("utf-8")

        def _publish(channel: _RabbitMqChannel) -> None:
            import pika

            self._declare_queue(channel, envelope.queue)
            channel.basic_publish(
                exchange="",
                routing_key=envelope.queue,
                body=body,
                properties=pika.BasicProperties(delivery_mode=2),
            )

        self._with_channel(_publish)

    def consume_one(self, queue: str | None = None) -> QueueEnvelope | None:
        target_queues: list[str]
        if queue is not None:
            target_queues = [queue]
        else:
            target_queues = ["realtime.queue", "normal.queue", "memory.queue", "batch.queue"]

        def _consume(channel: _RabbitMqChannel) -> QueueEnvelope | None:
            for queue_name in target_queues:
                self._declare_queue(channel, queue_name)
                method_frame, _, body = channel.basic_get(queue=queue_name, auto_ack=False)
                if method_frame is None:
                    continue
                channel.basic_ack(method_frame.delivery_tag)
                payload = json.loads(body.decode("utf-8"))
                return QueueEnvelope.from_dict(payload)
            return None

        return self._with_channel(_consume)

    def requeue_or_dead_letter(
        self,
        envelope: QueueEnvelope,
        *,
        attempts: int,
        max_attempts: int,
        retry_delay_seconds: float,
        error_message: str,
    ) -> dict[str, Any]:
        if attempts < max_attempts:
            if retry_delay_seconds > 0:
                delay_ms = max(int(retry_delay_seconds * 1000), 1)
                retry_queue = f"{envelope.queue}.retry"
                body = json.dumps(envelope.to_dict(), ensure_ascii=True).encode("utf-8")

                def _publish_retry(channel: _RabbitMqChannel) -> None:
                    import pika

                    channel.queue_declare(
                        queue=retry_queue,
                        durable=True,
                        arguments={
                            "x-dead-letter-exchange": "",
                            "x-dead-letter-routing-key": envelope.queue,
                        },
                    )
                    channel.basic_publish(
                        exchange="",
                        routing_key=retry_queue,
                        body=body,
                        properties=pika.BasicProperties(
                            delivery_mode=2,
                            expiration=str(delay_ms),
                        ),
                    )

                self._with_channel(_publish_retry)
            else:
                self.publish(envelope)

            return {
                "action": "requeued",
                "backend": "rabbitmq",
                "queue": envelope.queue,
                "attempts": attempts,
                "max_attempts": max_attempts,
                "retry_delay_seconds": float(retry_delay_seconds),
                "retry_strategy": "ttl_dead_letter",
            }

        dead_queue = f"{envelope.queue}.dead"
        dead_payload = {
            **envelope.to_dict(),
            "dead_reason": error_message,
        }
        body = json.dumps(dead_payload, ensure_ascii=True).encode("utf-8")

        def _publish_dead(channel: _RabbitMqChannel) -> None:
            self._declare_queue(channel, dead_queue)
            channel.basic_publish(exchange="", routing_key=dead_queue, body=body)

        self._with_channel(_publish_dead)
        return {
            "action": "dead_lettered",
            "backend": "rabbitmq",
            "queue": dead_queue,
            "attempts": attempts,
            "max_attempts": max_attempts,
            "retry_delay_seconds": 0.0,
        }


class TaskQueueService:
    """Queue facade with fail-open fallback to in-memory backend."""

    def __init__(self) -> None:
        self._memory = InMemoryQueueBackend()
        self._rabbit = RabbitMqQueueBackend(settings.rabbitmq_url)

    def _preferred_backend_name(self) -> str:
        return settings.task_queue_backend

    def _choose_backend(self, *, force_memory: bool = False) -> BaseTaskQueueBackend:
        if force_memory:
            return self._memory
        if self._preferred_backend_name() == "rabbitmq":
            return self._rabbit
        return self._memory

    @staticmethod
    def _is_recoverable_queue_error(exc: Exception) -> bool:
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return True

        try:
            import pika

            recoverable_names = (
                "AMQPConnectionError",
                "AMQPChannelError",
                "ChannelWrongStateError",
                "ConnectionClosed",
                "ConnectionWrongStateError",
                "StreamLostError",
            )
            recoverable_types = tuple(
                getattr(pika.exceptions, name)
                for name in recoverable_names
                if hasattr(pika.exceptions, name)
            )
            return bool(recoverable_types) and isinstance(exc, recoverable_types)
        except Exception:
            return False

    def _exec_with_fallback(
        self,
        op_name: str,
        fn: Callable[[BaseTaskQueueBackend], QueueOpResult],
    ) -> QueueOpResult:
        backend = self._choose_backend()
        try:
            return fn(backend)
        except Exception as exc:
            preferred = self._preferred_backend_name()
            if (
                preferred == "rabbitmq"
                and settings.task_queue_fail_open
                and self._is_recoverable_queue_error(exc)
            ):
                logger.warning(
                    "Queue op %s failed on rabbitmq backend, fallback to memory backend: %s",
                    op_name,
                    exc,
                )
                fallback_result = fn(self._memory)
                if isinstance(fallback_result, dict):
                    fallback_payload = dict(fallback_result)
                    fallback_payload.setdefault("fallback_from", "rabbitmq")
                    fallback_payload.setdefault("fallback_reason", str(exc))
                    return cast(QueueOpResult, fallback_payload)
                return fallback_result
            raise HelioraError(
                code="TASK_QUEUE_UNAVAILABLE",
                status_code=503,
                message=f"task queue backend unavailable: {exc}",
            ) from exc

    def publish(self, envelope: QueueEnvelope) -> None:
        self._exec_with_fallback("publish", lambda backend: backend.publish(envelope))

    def consume_one(self, queue: str | None = None) -> QueueEnvelope | None:
        return self._exec_with_fallback(
            "consume_one",
            lambda backend: backend.consume_one(queue=queue),
        )

    def requeue_or_dead_letter(
        self,
        envelope: QueueEnvelope,
        *,
        attempts: int,
        retry_delay_seconds: float,
        error_message: str,
    ) -> dict[str, Any]:
        return self._exec_with_fallback(
            "requeue_or_dead_letter",
            lambda backend: backend.requeue_or_dead_letter(
                envelope,
                attempts=attempts,
                max_attempts=settings.task_retry_max_attempts,
                retry_delay_seconds=retry_delay_seconds,
                error_message=error_message,
            ),
        )


task_queue_service = TaskQueueService()
