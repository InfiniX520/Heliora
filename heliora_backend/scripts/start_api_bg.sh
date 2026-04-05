#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${ROOT_DIR}/.api.log"

cd "${ROOT_DIR}"

if pgrep -f "python main.py|uvicorn.*app.main:app" >/dev/null 2>&1; then
  echo "API seems to be already running."
  echo "Health: http://127.0.0.1:8000/health"
  if [ "${START_TASK_WORKER_WITH_API:-true}" = "true" ]; then
    bash scripts/start_worker_bg.sh || true
  fi
  exit 0
fi

if [ ! -d ".venv" ]; then
  echo "Missing .venv. Run: bash scripts/bootstrap_dev.sh"
  exit 1
fi

source .venv/bin/activate
nohup python main.py >"${LOG_FILE}" 2>&1 &

sleep 2
if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "API started in background."
  echo "Log: ${LOG_FILE}"
  echo "Health: http://127.0.0.1:8000/health"
  if [ "${START_TASK_WORKER_WITH_API:-true}" = "true" ]; then
    if ! bash scripts/start_worker_bg.sh; then
      echo "Warning: worker failed to start."
    fi
  fi
  exit 0
fi

echo "API failed to start. Recent log:"
tail -n 80 "${LOG_FILE}" || true
exit 1
