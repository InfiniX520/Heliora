#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${ROOT_DIR}/.worker.log"
PID_FILE="${ROOT_DIR}/.worker.pid"

cd "${ROOT_DIR}"

if [ -f "${PID_FILE}" ]; then
  OLD_PID="$(cat "${PID_FILE}")"
  if [ -n "${OLD_PID}" ] && kill -0 "${OLD_PID}" >/dev/null 2>&1; then
    echo "Worker already running (PID ${OLD_PID})."
    echo "Log: ${LOG_FILE}"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

if [ ! -d ".venv" ]; then
  echo "Missing .venv. Run: bash scripts/bootstrap_dev.sh"
  exit 1
fi

source .venv/bin/activate
nohup python scripts/task_consumer_daemon.py >"${LOG_FILE}" 2>&1 &
NEW_PID="$!"
echo "${NEW_PID}" >"${PID_FILE}"

sleep 1
if kill -0 "${NEW_PID}" >/dev/null 2>&1; then
  echo "Worker started in background."
  echo "PID: ${NEW_PID}"
  echo "Log: ${LOG_FILE}"
  exit 0
fi

echo "Worker failed to start. Recent log:"
tail -n 80 "${LOG_FILE}" || true
exit 1
