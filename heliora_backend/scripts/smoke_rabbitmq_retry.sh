#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TRACE_ID="trc_rmq_smoke_$(date +%s)"
IDEMPOTENCY_KEY="idem_rmq_smoke_$(date +%s)"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-45}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-1}"

cd "${ROOT_DIR}"

resolve_python_bin() {
  if [ -x ".venv/bin/python" ]; then
    echo ".venv/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  return 1
}

if ! PYTHON_BIN="$(resolve_python_bin)"; then
  echo "Python interpreter not found. Install python3 or create .venv first."
  exit 1
fi

if [ "${AUTO_START_API_WORKER:-true}" = "true" ]; then
  bash scripts/start_api_bg.sh >/dev/null
fi

echo "[1/4] GET /health"
curl -fsS -H "X-Trace-Id: ${TRACE_ID}" "${BASE_URL}/health" >/dev/null
echo "ok"

echo "[2/4] Ensure queue backend config"
QUEUE_BACKEND="$("${PYTHON_BIN}" - <<'PY'
from pathlib import Path

env_file = Path('.env')
if not env_file.exists():
    print('')
    raise SystemExit(0)

value = ''
for raw_line in env_file.read_text(encoding='utf-8', errors='ignore').splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, raw_value = line.split('=', 1)
    if key.strip() != 'TASK_QUEUE_BACKEND':
        continue
    value = raw_value.strip().strip('"').strip("'").lower()
    break

print(value)
PY
)"

if [ "${QUEUE_BACKEND}" = "rabbitmq" ]; then
  echo "TASK_QUEUE_BACKEND=rabbitmq"
else
  echo "TASK_QUEUE_BACKEND is '${QUEUE_BACKEND:-unset}', expected 'rabbitmq'."
  echo "Set TASK_QUEUE_BACKEND=rabbitmq in .env, restart API+worker, then rerun this script."
  exit 1
fi

echo "[2.5/4] Preflight RabbitMQ runtime"
if ! "${PYTHON_BIN}" -c "import pika" >/dev/null 2>&1; then
  echo "Missing Python package 'pika' in current runtime (${PYTHON_BIN})."
  echo "Install with: source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

RABBIT_PREFLIGHT="$("${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import os
from pathlib import Path

import pika


def read_env_value(key: str) -> str:
    env_file = Path('.env')
    if not env_file.exists():
        return ''

    for raw_line in env_file.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, raw_value = line.split('=', 1)
        if k.strip() != key:
            continue
        return raw_value.strip().strip('"').strip("'")
    return ''


amqp_url = os.getenv('RABBITMQ_URL') or read_env_value('RABBITMQ_URL')
if not amqp_url:
    print('error:missing_rabbitmq_url')
    raise SystemExit(0)

try:
    params = pika.URLParameters(amqp_url)
    connection = pika.BlockingConnection(params)
    connection.close()
except Exception as exc:  # pragma: no cover - runtime preflight
    print(f'error:rabbit_connect_failed:{exc}')
    raise SystemExit(0)

print('ok')
PY
)"

if [ "${RABBIT_PREFLIGHT}" != "ok" ]; then
  echo "RabbitMQ preflight failed: ${RABBIT_PREFLIGHT}"
  echo "Check .env RABBITMQ_URL, container status, and credentials."
  exit 1
fi
echo "RabbitMQ preflight ok"

echo "[3/4] Submit force-fail task"
SUBMIT_RESP="$(curl -fsS -X POST "${BASE_URL}/api/v1/tasks/submit" \
  -H "Content-Type: application/json" \
  -H "X-Trace-Id: ${TRACE_ID}" \
  -H "Idempotency-Key: ${IDEMPOTENCY_KEY}" \
  -d '{"task_type":"retry_probe","priority":"P2","required_capabilities":["worker"],"payload":{"force_fail":true}}')"

TASK_ID="$("${PYTHON_BIN}" - <<'PY' "${SUBMIT_RESP}"
import json
import sys
body = json.loads(sys.argv[1])
print(body["data"]["task_id"])
PY
)"

echo "task_id=${TASK_ID}"

echo "[4/4] Poll events until dead_lettered"
START_TS="$(date +%s)"
while true; do
  EVENTS_RESP="$(curl -fsS -H "X-Trace-Id: ${TRACE_ID}" "${BASE_URL}/api/v1/tasks/${TASK_ID}/events")"
  STATUS_LINE="$("${PYTHON_BIN}" - <<'PY' "${EVENTS_RESP}"
import json
import sys
body = json.loads(sys.argv[1])
events = body.get("data", {}).get("events", [])
failed = [evt for evt in events if evt.get("event_type") == "failed"]
if not failed:
    print("pending|0|none|unknown")
    raise SystemExit(0)
last = failed[-1]
meta = last.get("metadata") or {}
action = meta.get("action", "none")
attempts = meta.get("attempts", 0)
backend = meta.get("backend", "unknown")
fallback_reason = str(meta.get("fallback_reason", "")).replace("|", "/").replace("\n", " ")
print(f"{action}|{attempts}|{len(events)}|{backend}|{fallback_reason}")
PY
)"

  ACTION="${STATUS_LINE%%|*}"
  REST="${STATUS_LINE#*|}"
  ATTEMPTS="${REST%%|*}"
  REST2="${REST#*|}"
  EVENTS_COUNT="${REST2%%|*}"
  REST3="${REST2#*|}"
  BACKEND="${REST3%%|*}"
  FALLBACK_REASON="${STATUS_LINE##*|}"

  echo "events=${EVENTS_COUNT} action=${ACTION} attempts=${ATTEMPTS} backend=${BACKEND}"

  if [ "${ACTION}" = "dead_lettered" ]; then
    if [ "${BACKEND}" = "rabbitmq" ]; then
      echo "RabbitMQ retry smoke passed (dead_lettered observed with backend=rabbitmq)."
      break
    fi
    echo "dead_lettered observed but backend=${BACKEND}, expected rabbitmq."
    if [ -n "${FALLBACK_REASON}" ]; then
      echo "fallback_reason=${FALLBACK_REASON}"
    fi
    echo "This usually means queue fail-open fallback to memory was triggered."
    exit 1
  fi

  NOW_TS="$(date +%s)"
  ELAPSED="$((NOW_TS - START_TS))"
  if [ "${ELAPSED}" -ge "${MAX_WAIT_SECONDS}" ]; then
    echo "Timeout waiting for dead_lettered action."
    exit 1
  fi

  sleep "${POLL_INTERVAL_SECONDS}"
done
