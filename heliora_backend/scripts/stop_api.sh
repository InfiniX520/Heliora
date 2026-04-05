#!/usr/bin/env bash
set -euo pipefail

PIDS="$(pgrep -f "python main.py|uvicorn.*app.main:app" || true)"

if [ -z "${PIDS}" ]; then
  echo "API is not running."
  if [ "${STOP_TASK_WORKER_WITH_API:-true}" = "true" ]; then
    bash scripts/stop_worker.sh || true
  fi
  exit 0
fi

echo "Stopping API PIDs: ${PIDS}"
kill ${PIDS}
sleep 1

LEFT="$(pgrep -f "python main.py|uvicorn.*app.main:app" || true)"
if [ -n "${LEFT}" ]; then
  echo "Force killing remaining PIDs: ${LEFT}"
  kill -9 ${LEFT}
fi

if [ "${STOP_TASK_WORKER_WITH_API:-true}" = "true" ]; then
  bash scripts/stop_worker.sh || true
fi

echo "API stopped."
