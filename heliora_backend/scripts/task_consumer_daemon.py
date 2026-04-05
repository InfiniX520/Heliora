#!/usr/bin/env python
"""Background task consumer daemon that continuously calls consume-next endpoint."""

from __future__ import annotations

import argparse
import logging
import os
import re
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


_STOP = False
_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
logger = logging.getLogger("task_consumer_daemon")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _handle_stop_signal(signum: int, frame: object) -> None:  # noqa: ARG001
    global _STOP
    _STOP = True


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError:
        return default
    if value < 0:
        return default
    return value


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _load_env_file(env_file: Path, *, overwrite: bool = False) -> None:
    """Load KEY=VALUE lines from .env safely without shell sourcing."""
    if not env_file.exists():
        return

    text = env_file.read_text(encoding="utf-8", errors="ignore")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY_PATTERN.match(key):
            continue

        value = _strip_matching_quotes(value.strip())
        if overwrite or key not in os.environ:
            os.environ[key] = value


def _build_payload(queue: str | None, force_fail: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {"force_fail": force_fail}
    if queue:
        payload["queue"] = queue
    return payload


def _consume_once(
    client: httpx.Client,
    *,
    api_base_url: str,
    queue: str | None,
    force_fail: bool,
    trace_prefix: str,
) -> dict[str, Any]:
    endpoint = f"{api_base_url.rstrip('/')}/api/v1/tasks/consume-next"
    trace_id = f"{trace_prefix}_{int(time.time() * 1000)}"
    response = client.post(
        endpoint,
        headers={"X-Trace-Id": trace_id},
        json=_build_payload(queue, force_fail),
        timeout=15.0,
    )
    response.raise_for_status()
    body = response.json()
    return {
        "code": body.get("code", "UNKNOWN"),
        "message": body.get("message", ""),
        "task_id": ((body.get("data") or {}).get("task") or {}).get("task_id"),
    }


def run_loop(
    *,
    api_base_url: str,
    queue: str | None,
    force_fail: bool,
    idle_seconds: float,
    busy_seconds: float,
    error_backoff_seconds: float,
    trace_prefix: str,
    once: bool,
) -> int:
    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)

    logger.info(
        "worker started ts=%s api=%s queue=%s once=%s",
        _utc_now_iso(),
        api_base_url,
        queue or "all",
        once,
    )

    with httpx.Client() as client:
        while not _STOP:
            try:
                result = _consume_once(
                    client,
                    api_base_url=api_base_url,
                    queue=queue,
                    force_fail=force_fail,
                    trace_prefix=trace_prefix,
                )
                if result["code"] == "NOOP":
                    logger.info("no queued task ts=%s", _utc_now_iso())
                    if once:
                        return 0
                    time.sleep(idle_seconds)
                    continue

                task_id = result.get("task_id") or "unknown"
                logger.info(
                    "consumed task ts=%s task_id=%s code=%s message=%s",
                    _utc_now_iso(),
                    task_id,
                    result["code"],
                    result["message"],
                )
                if once:
                    return 0
                time.sleep(busy_seconds)
            except Exception as exc:  # pragma: no cover - integration path
                logger.error("worker error ts=%s error=%s", _utc_now_iso(), exc)
                if once:
                    return 1
                time.sleep(error_backoff_seconds)

    logger.info("worker stopped ts=%s", _utc_now_iso())
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Heliora task consumer daemon")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Consume at most one task and exit.",
    )
    parser.add_argument(
        "--queue",
        default=os.getenv("TASK_WORKER_QUEUE", ""),
        help="Target queue name. Empty means consume from default queue order.",
    )
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("TASK_WORKER_API_BASE_URL", "http://127.0.0.1:8000"),
        help="API base URL for consume-next endpoint.",
    )
    parser.add_argument(
        "--force-fail",
        action="store_true",
        help="Set force_fail=true when calling consume-next (test-only).",
    )
    parser.add_argument(
        "--trace-prefix",
        default=os.getenv("TASK_WORKER_TRACE_PREFIX", "trc_worker"),
        help="Trace-id prefix used for consume-next calls.",
    )
    return parser.parse_args()


def main() -> int:
    backend_root = Path(__file__).resolve().parents[1]
    _load_env_file(backend_root / ".env")
    logging.basicConfig(
        level=os.getenv("TASK_WORKER_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    args = parse_args()
    queue = args.queue.strip() or None
    return run_loop(
        api_base_url=args.api_base_url.strip(),
        queue=queue,
        force_fail=args.force_fail,
        idle_seconds=_env_float("TASK_WORKER_IDLE_SECONDS", 1.0),
        busy_seconds=_env_float("TASK_WORKER_BUSY_SECONDS", 0.1),
        error_backoff_seconds=_env_float("TASK_WORKER_ERROR_BACKOFF_SECONDS", 2.0),
        trace_prefix=args.trace_prefix.strip(),
        once=bool(args.once),
    )


if __name__ == "__main__":
    raise SystemExit(main())
