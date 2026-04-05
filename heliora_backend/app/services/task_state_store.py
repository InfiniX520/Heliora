"""Task state persistence store (SQLite)."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, cast

from app.core.config import BACKEND_ROOT, settings


logger = logging.getLogger(__name__)


class _PostgresCursor(Protocol):
    def __enter__(self) -> "_PostgresCursor": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...

    def execute(self, query: str, params: tuple[object, ...] | list[object] | None = None) -> None: ...

    def fetchone(self) -> tuple[object, ...] | None: ...


class _PostgresConnection(Protocol):
    def __enter__(self) -> "_PostgresConnection": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...

    def cursor(self) -> _PostgresCursor: ...


class TaskStateStore:
    """Persist task snapshots for status durability."""

    def __init__(self) -> None:
        self._backend = settings.task_persistence_backend
        self._postgres_dsn = self._resolve_postgres_dsn()
        raw_path = Path(settings.task_registry_sqlite_path)
        if raw_path.is_absolute():
            self._db_path = raw_path
        else:
            self._db_path = BACKEND_ROOT / raw_path
        self._enabled = bool(settings.task_registry_persistence_enabled)
        if self._enabled:
            if self._backend == "sqlite":
                self._ensure_sqlite_schema()
            else:
                self._validate_postgres_backend()

    def _resolve_postgres_dsn(self) -> str:
        return (settings.task_registry_postgres_dsn or settings.database_url).strip()

    def _validate_postgres_backend(self) -> None:
        if not self._postgres_dsn:
            raise RuntimeError(
                "task_persistence_backend=postgres requires "
                "task_registry_postgres_dsn or database_url"
            )

    def _get_postgres_connection(self) -> _PostgresConnection:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError(
                "psycopg is required when task_persistence_backend=postgres"
            ) from exc

        return cast(_PostgresConnection, psycopg.connect(self._postgres_dsn))

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_sqlite_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_registry (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_registry_status ON task_registry(status)"
            )

    def save_task(self, task: dict[str, Any]) -> None:
        if not self._enabled:
            return

        payload_json = json.dumps(task, ensure_ascii=False)
        task_id = str(task["task_id"])
        status = str(task.get("status") or "queued")
        created_at = str(task.get("created_at") or task.get("updated_at") or "")
        updated_at = str(task.get("updated_at") or task.get("created_at") or created_at)

        if self._backend == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO task_registry(task_id, status, payload_json, created_at, updated_at)
                        VALUES (%s, %s, %s::jsonb, %s::timestamptz, %s::timestamptz)
                        ON CONFLICT(task_id) DO UPDATE SET
                            status=EXCLUDED.status,
                            payload_json=EXCLUDED.payload_json,
                            updated_at=EXCLUDED.updated_at
                        """,
                        (task_id, status, payload_json, created_at, updated_at),
                    )
            return

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO task_registry(task_id, status, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status=excluded.status,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (task_id, status, payload_json, updated_at),
            )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        if not self._enabled:
            return None

        if self._backend == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT payload_json
                        FROM task_registry
                        WHERE task_id = %s
                        LIMIT 1
                        """,
                        (task_id,),
                    )
                    row = cur.fetchone()

            if row is None:
                return None

            payload = row[0]
            if isinstance(payload, dict):
                return payload
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode("utf-8", errors="ignore")

            if isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    logger.warning(
                        "Invalid task payload JSON in task_registry for task_id=%s",
                        task_id,
                    )
            return None

        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM task_registry
                WHERE task_id = ?
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()

        if row is None:
            return None

        try:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict):
                return None
            return payload
        except json.JSONDecodeError:
            logger.warning("Invalid task payload JSON in task_registry for task_id=%s", task_id)
            return None

    def clear(self) -> None:
        if not self._enabled:
            return

        if self._backend == "postgres":
            try:
                with self._get_postgres_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM task_registry")
            except Exception as exc:  # pragma: no cover - FK/governance constrained path
                logger.info("skip task_registry clear on postgres backend: %s", exc)
            return

        with self._get_connection() as conn:
            conn.execute("DELETE FROM task_registry")


_task_state_store_singleton = TaskStateStore()


def get_task_state_store() -> TaskStateStore:
    return _task_state_store_singleton


task_state_store = get_task_state_store()
