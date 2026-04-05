"""Task event persistence store (SQLite)."""

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

    def fetchall(self) -> list[tuple[object, ...]]: ...


class _PostgresConnection(Protocol):
    def __enter__(self) -> "_PostgresConnection": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...

    def cursor(self) -> _PostgresCursor: ...


class TaskEventStore:
    """Persist task events for audit durability."""

    def __init__(self) -> None:
        self._backend = settings.task_persistence_backend
        self._postgres_dsn = self._resolve_postgres_dsn()
        raw_path = Path(settings.task_events_sqlite_path)
        if raw_path.is_absolute():
            self._db_path = raw_path
        else:
            self._db_path = BACKEND_ROOT / raw_path
        self._enabled = bool(settings.task_events_persistence_enabled)
        if self._enabled:
            if self._backend == "sqlite":
                self._ensure_sqlite_schema()
            else:
                self._validate_postgres_backend()

    def _resolve_postgres_dsn(self) -> str:
        return (settings.task_events_postgres_dsn or settings.database_url).strip()

    def _validate_postgres_backend(self) -> None:
        if not self._postgres_dsn:
            raise RuntimeError(
                "task_persistence_backend=postgres requires "
                "task_events_postgres_dsn or database_url"
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
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    ts TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_events_task_id_ts ON task_events(task_id, id)"
            )

    def save_event(self, event: dict[str, Any]) -> None:
        if not self._enabled:
            return

        metadata_json = json.dumps(event.get("metadata") or {}, ensure_ascii=False)

        if self._backend == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO task_events(
                            event_id,
                            task_id,
                            event_type,
                            from_status,
                            to_status,
                            message,
                            metadata_json,
                            ts
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::timestamptz)
                        ON CONFLICT (event_id) DO NOTHING
                        """,
                        (
                            str(event["event_id"]),
                            str(event["task_id"]),
                            str(event["event_type"]),
                            event.get("from_status"),
                            str(event["to_status"]),
                            str(event["message"]),
                            metadata_json,
                            str(event["ts"]),
                        ),
                    )
            return

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO task_events(
                    event_id,
                    task_id,
                    event_type,
                    from_status,
                    to_status,
                    message,
                    metadata_json,
                    ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event["event_id"]),
                    str(event["task_id"]),
                    str(event["event_type"]),
                    event.get("from_status"),
                    str(event["to_status"]),
                    str(event["message"]),
                    metadata_json,
                    str(event["ts"]),
                ),
            )

    def count_events(
        self,
        task_id: str,
        *,
        event_type: str | None = None,
        start_ts: str | None = None,
        end_ts: str | None = None,
    ) -> int:
        """Count task events with optional filtering conditions."""
        if not self._enabled:
            return 0

        if self._backend == "postgres":
            clauses = ["task_id = %s"]
            pg_params: list[Any] = [task_id]
            if event_type:
                clauses.append("event_type = %s")
                pg_params.append(event_type)
            if start_ts:
                clauses.append("ts >= %s::timestamptz")
                pg_params.append(start_ts)
            if end_ts:
                clauses.append("ts <= %s::timestamptz")
                pg_params.append(end_ts)

            query = f"SELECT COUNT(1) FROM task_events WHERE {' AND '.join(clauses)}"
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, pg_params)
                    pg_row = cur.fetchone()
            if pg_row is None:
                return 0
            return cast(int, pg_row[0])

        query = "SELECT COUNT(1) FROM task_events WHERE task_id = ?"
        sqlite_params: list[Any] = [task_id]
        if event_type:
            query += " AND event_type = ?"
            sqlite_params.append(event_type)
        if start_ts:
            query += " AND ts >= ?"
            sqlite_params.append(start_ts)
        if end_ts:
            query += " AND ts <= ?"
            sqlite_params.append(end_ts)

        with self._get_connection() as conn:
            sqlite_row = conn.execute(query, sqlite_params).fetchone()
        if sqlite_row is None:
            return 0
        return cast(int, sqlite_row[0])

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
        if not self._enabled:
            return []

        if self._backend == "postgres":
            clauses = ["task_id = %s"]
            pg_params: list[Any] = [task_id]
            if event_type:
                clauses.append("event_type = %s")
                pg_params.append(event_type)
            if start_ts:
                clauses.append("ts >= %s::timestamptz")
                pg_params.append(start_ts)
            if end_ts:
                clauses.append("ts <= %s::timestamptz")
                pg_params.append(end_ts)

            query = f"""
                SELECT
                    event_id,
                    task_id,
                    event_type,
                    from_status,
                    to_status,
                    message,
                    metadata_json,
                    ts
                FROM task_events
                WHERE {' AND '.join(clauses)}
                ORDER BY ts ASC, event_id ASC
                LIMIT %s OFFSET %s
            """
            pg_params.extend([limit, offset])

            with self._get_postgres_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, pg_params)
                    pg_rows = cur.fetchall()

            pg_events: list[dict[str, Any]] = []
            for row in pg_rows:
                metadata = row[6]
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Invalid metadata JSON in task_events for event_id=%s",
                            row[0],
                        )
                        metadata = {}

                pg_events.append(
                    {
                        "event_id": row[0],
                        "task_id": row[1],
                        "event_type": row[2],
                        "from_status": row[3],
                        "to_status": row[4],
                        "message": row[5],
                        "metadata": metadata if isinstance(metadata, dict) else {},
                        "ts": str(row[7]),
                    }
                )

            return pg_events

        query = (
            """
                SELECT
                    event_id,
                    task_id,
                    event_type,
                    from_status,
                    to_status,
                    message,
                    metadata_json,
                    ts
                FROM task_events
                WHERE task_id = ?
            """
        )
        sqlite_params: list[Any] = [task_id]
        if event_type:
            query += " AND event_type = ?"
            sqlite_params.append(event_type)
        if start_ts:
            query += " AND ts >= ?"
            sqlite_params.append(start_ts)
        if end_ts:
            query += " AND ts <= ?"
            sqlite_params.append(end_ts)

        query += " ORDER BY id ASC LIMIT ? OFFSET ?"
        sqlite_params.extend([limit, offset])

        with self._get_connection() as conn:
            sqlite_rows = conn.execute(query, sqlite_params).fetchall()

        sqlite_events: list[dict[str, Any]] = []
        for row in sqlite_rows:
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                logger.warning("Invalid metadata JSON in task_events for event_id=%s", row["event_id"])
                metadata = {}
            sqlite_events.append(
                {
                    "event_id": row["event_id"],
                    "task_id": row["task_id"],
                    "event_type": row["event_type"],
                    "from_status": row["from_status"],
                    "to_status": row["to_status"],
                    "message": row["message"],
                    "metadata": metadata,
                    "ts": row["ts"],
                }
            )

        return sqlite_events

    def clear(self) -> None:
        if not self._enabled:
            return

        if self._backend == "postgres":
            try:
                with self._get_postgres_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM task_events")
            except Exception as exc:  # pragma: no cover - governance-constrained path
                logger.info("skip task_events clear on postgres backend: %s", exc)
            return

        with self._get_connection() as conn:
            conn.execute("DELETE FROM task_events")


_task_event_store_singleton = TaskEventStore()


def get_task_event_store() -> TaskEventStore:
    return _task_event_store_singleton


task_event_store = get_task_event_store()
