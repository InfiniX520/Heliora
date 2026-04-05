"""In-memory idempotency store for scaffold-stage task submission."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.errors import HelioraError


@dataclass
class IdempotencyRecord:
    """Stored idempotency record payload."""

    fingerprint: str
    response_data: dict[str, Any]
    expires_at: float


class InMemoryIdempotencyStore:
    """Simple process-local idempotency storage with TTL."""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self.ttl_seconds = ttl_seconds
        self._records: dict[str, IdempotencyRecord] = {}
        self._lock = threading.Lock()

    @staticmethod
    def build_fingerprint(payload: dict[str, Any]) -> str:
        """Build a deterministic hash for a request payload."""
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _purge_expired_unlocked(self, now: float) -> None:
        expired_keys = [key for key, record in self._records.items() if record.expires_at <= now]
        for key in expired_keys:
            self._records.pop(key, None)

    def get_replay(self, idempotency_key: str, fingerprint: str) -> dict[str, Any] | None:
        """Return a replay payload when key+payload are repeated."""
        now = time.time()
        with self._lock:
            self._purge_expired_unlocked(now)
            record = self._records.get(idempotency_key)
            if record is None:
                return None

            if record.fingerprint != fingerprint:
                raise HelioraError(
                    code="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
                    status_code=409,
                    message="Idempotency-Key cannot be reused with a different payload",
                )

            return record.response_data

    def save(self, idempotency_key: str, fingerprint: str, response_data: dict[str, Any]) -> None:
        """Store task response for idempotent replay."""
        now = time.time()
        with self._lock:
            self._purge_expired_unlocked(now)
            self._records[idempotency_key] = IdempotencyRecord(
                fingerprint=fingerprint,
                response_data=response_data,
                expires_at=now + self.ttl_seconds,
            )

    def clear(self) -> None:
        """Clear all records; used by tests only."""
        with self._lock:
            self._records.clear()


idempotency_store = InMemoryIdempotencyStore(ttl_seconds=settings.idempotency_ttl_seconds)
