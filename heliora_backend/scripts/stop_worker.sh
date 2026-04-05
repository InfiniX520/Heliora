#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${ROOT_DIR}/.worker.pid"

cd "${ROOT_DIR}"

if [ -f "${PID_FILE}" ]; then
  PID="$(cat "${PID_FILE}")"
  if [ -n "${PID}" ] && kill -0 "${PID}" >/dev/null 2>&1; then
    echo "Stopping worker PID: ${PID}"
    kill "${PID}" || true
    sleep 1
    if kill -0 "${PID}" >/dev/null 2>&1; then
      echo "Force killing worker PID: ${PID}"
      kill -9 "${PID}" || true
    fi
    rm -f "${PID_FILE}"
    echo "Worker stopped."
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

PIDS="$(pgrep -f "task_consumer_daemon.py" || true)"
if [ -n "${PIDS}" ]; then
  echo "Stopping worker PIDs: ${PIDS}"
  kill ${PIDS} || true
  sleep 1
  LEFT="$(pgrep -f "task_consumer_daemon.py" || true)"
  if [ -n "${LEFT}" ]; then
    echo "Force killing worker PIDs: ${LEFT}"
    kill -9 ${LEFT} || true
  fi
  echo "Worker stopped."
  exit 0
fi

echo "Worker is not running."
