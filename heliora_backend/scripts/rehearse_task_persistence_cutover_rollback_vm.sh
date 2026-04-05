#!/usr/bin/env bash
set -euo pipefail

# Host-side helper: rehearse cutover to postgres and rollback to sqlite on VM.
# Steps:
#   1) Run postgres runtime matrix (memory + rabbitmq queue backends)
#   2) Verify rollback path by running sqlite profile regression

SSH_BIN="${SSH_BIN:-}"
SSH_HOST="${SSH_HOST:-Heliora-VM}"
REMOTE_BACKEND_DIR="${REMOTE_BACKEND_DIR:-}"
ROLLBACK_PYTEST_TARGET="${ROLLBACK_PYTEST_TARGET:-tests/test_tasks_submit.py}"

detect_ssh_bin() {
  local candidate

  if [[ -n "${SSH_BIN}" ]]; then
    if [[ -x "${SSH_BIN}" ]]; then
      printf '%s\n' "${SSH_BIN}"
      return 0
    fi
    return 1
  fi

  candidate="$(command -v ssh 2>/dev/null || true)"
  if [[ -n "${candidate}" ]]; then
    printf '%s\n' "${candidate}"
    return 0
  fi

  for candidate in \
    "/e/Git_A/Git/usr/bin/ssh.exe" \
    "/e/Git_A/Git/bin/ssh.exe"
  do
    if [[ -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  return 1
}

if ! SSH_BIN="$(detect_ssh_bin)"; then
  echo "ssh client not found."
  echo "Set SSH_BIN to your ssh executable path."
  exit 1
fi

ssh_exec() {
  "${SSH_BIN}" -F "${HOME}/.ssh/config" "$@"
}

if ! ssh_exec -o BatchMode=yes "${SSH_HOST}" "echo connected" >/dev/null 2>&1; then
  echo "Cannot login to ${SSH_HOST} in batch mode."
  echo "Ensure SSH key login works first."
  exit 1
fi

if [[ -z "${REMOTE_BACKEND_DIR}" ]]; then
  REMOTE_BACKEND_DIR="$(ssh_exec "${SSH_HOST}" "for d in \
    \"\$HOME/heliora_backend\" \
    \"\$HOME/Heliora/heliora_backend\" \
    \"\$HOME/Zero9/Heliora/heliora_backend\" \
    \"\$HOME/work/Heliora/heliora_backend\"; do \
      if [ -d \"\$d\" ]; then echo \"\$d\"; break; fi; \
    done")"
fi

if [[ -z "${REMOTE_BACKEND_DIR}" ]]; then
  echo "Cannot detect remote backend path."
  echo "Set REMOTE_BACKEND_DIR and rerun."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MATRIX_SCRIPT="${SCRIPT_DIR}/run_task_persistence_pg_matrix_vm.sh"

if [[ ! -f "${MATRIX_SCRIPT}" ]]; then
  echo "matrix helper not found: ${MATRIX_SCRIPT}"
  exit 1
fi

echo "[rehearsal] start postgres cutover matrix"
SSH_BIN="${SSH_BIN}" SSH_HOST="${SSH_HOST}" REMOTE_BACKEND_DIR="${REMOTE_BACKEND_DIR}" \
  bash "${MATRIX_SCRIPT}"

echo "[rehearsal] start sqlite rollback validation"
ssh_exec "${SSH_HOST}" "
  set -euo pipefail
  cd '${REMOTE_BACKEND_DIR}'

  PYTHON_BIN='python3'
  if [ -x .venv/bin/python ]; then
    PYTHON_BIN='.venv/bin/python'
  fi

  TASK_PERSISTENCE_BACKEND='sqlite' \
  TASK_QUEUE_BACKEND='memory' \
  \"\${PYTHON_BIN}\" -m pytest ${ROLLBACK_PYTEST_TARGET} -q -rA
"

echo "[rehearsal] sqlite rollback validation passed"
echo "[rehearsal] cutover and rollback rehearsal passed"
