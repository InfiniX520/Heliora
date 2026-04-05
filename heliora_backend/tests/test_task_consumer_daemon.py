"""Tests for Day-3 task consumer daemon helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import TracebackType

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "task_consumer_daemon.py"
SPEC = importlib.util.spec_from_file_location("task_consumer_daemon", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
DAEMON = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DAEMON)


def test_build_payload_with_queue() -> None:
    payload = DAEMON._build_payload("normal.queue", False)

    assert payload == {"queue": "normal.queue", "force_fail": False}


def test_build_payload_without_queue() -> None:
    payload = DAEMON._build_payload(None, True)

    assert payload == {"force_fail": True}


def test_env_float_invalid_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASK_WORKER_IDLE_SECONDS", "bad-value")

    value = DAEMON._env_float("TASK_WORKER_IDLE_SECONDS", 1.5)

    assert value == 1.5


def test_run_loop_once_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyClient:
        def __enter__(self) -> "DummyClient":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool:  # noqa: ARG002
            return False

    def fake_consume_once(*args: object, **kwargs: object) -> dict[str, object | None]:  # noqa: ARG001
        return {"code": "NOOP", "message": "no queued task", "task_id": None}

    DAEMON._STOP = False
    monkeypatch.setattr(DAEMON.httpx, "Client", lambda: DummyClient())
    monkeypatch.setattr(DAEMON, "_consume_once", fake_consume_once)

    rc = DAEMON.run_loop(
        api_base_url="http://127.0.0.1:8000",
        queue="normal.queue",
        force_fail=False,
        idle_seconds=0,
        busy_seconds=0,
        error_backoff_seconds=0,
        trace_prefix="trc_test",
        once=True,
    )

    assert rc == 0


def test_load_env_file_handles_crlf_and_spaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_bytes(
        b"APP_NAME=Heliora Backend\r\nTASK_WORKER_QUEUE=normal.queue\r\n# comment\r\n"
    )

    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("TASK_WORKER_QUEUE", raising=False)

    DAEMON._load_env_file(env_file)

    assert DAEMON.os.environ["APP_NAME"] == "Heliora Backend"
    assert DAEMON.os.environ["TASK_WORKER_QUEUE"] == "normal.queue"


def test_load_env_file_does_not_override_existing_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TASK_WORKER_TRACE_PREFIX=from_file\n", encoding="utf-8")
    monkeypatch.setenv("TASK_WORKER_TRACE_PREFIX", "from_env")

    DAEMON._load_env_file(env_file)

    assert DAEMON.os.environ["TASK_WORKER_TRACE_PREFIX"] == "from_env"
