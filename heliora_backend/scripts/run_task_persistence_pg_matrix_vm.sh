#!/usr/bin/env bash
set -euo pipefail

# Host-side helper: run Day-4.2 PostgreSQL runtime regression matrix on VM.
# Matrix:
#   A) TASK_PERSISTENCE_BACKEND=postgres + TASK_QUEUE_BACKEND=memory
#   B) TASK_PERSISTENCE_BACKEND=postgres + TASK_QUEUE_BACKEND=rabbitmq

SSH_BIN="${SSH_BIN:-}"
SSH_HOST="${SSH_HOST:-Heliora-VM}"
REMOTE_BACKEND_DIR="${REMOTE_BACKEND_DIR:-}"
PG_CONTAINER="${PG_CONTAINER:-heliora-postgres}"
PGUSER_VALUE="${PGUSER_VALUE:-heliora}"
PGDATABASE_VALUE="${PGDATABASE_VALUE:-heliora}"

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

DB_URL="$(ssh_exec "${SSH_HOST}" "cd '${REMOTE_BACKEND_DIR}'; grep -E '^DATABASE_URL=' .env | cut -d= -f2-")"
if [[ -z "${DB_URL}" ]]; then
  echo "Cannot read DATABASE_URL from ${REMOTE_BACKEND_DIR}/.env"
  exit 1
fi

echo "[matrix] run env consistency preflight"
ssh_exec "${SSH_HOST}" "
  set -euo pipefail
  cd '${REMOTE_BACKEND_DIR}'
  PYTHON_BIN='python3'
  if [ -x .venv/bin/python ]; then
    PYTHON_BIN='.venv/bin/python'
  fi
  \"\${PYTHON_BIN}\" scripts/validate_env_consistency.py --env-file .env
"

if ! ssh_exec "${SSH_HOST}" "docker ps --format '{{.Names}}' | grep -qx '${PG_CONTAINER}'"; then
  echo "PostgreSQL container '${PG_CONTAINER}' is not running on VM."
  exit 1
fi

echo "[matrix] ssh ok: ${SSH_HOST}"
echo "[matrix] backend path: ${REMOTE_BACKEND_DIR}"
echo "[matrix] postgres container: ${PG_CONTAINER}"

after_each_profile_sql_down() {
  cat <<'EOS'
run_sql_file sql/task_persistence_pg/001_task_persistence_down.sql || true
EOS
}

run_profile() {
  local profile_name="$1"
  local queue_backend="$2"
  local pytest_target="$3"
  local rabbit_required="$4"

  echo "[profile:${profile_name}] start"

  ssh_exec "${SSH_HOST}" "
    set -euo pipefail
    cd '${REMOTE_BACKEND_DIR}'

    run_sql_file() {
      local sql_file=\"\$1\"
      docker exec -i '${PG_CONTAINER}' \
        psql -v ON_ERROR_STOP=1 -U '${PGUSER_VALUE}' -d '${PGDATABASE_VALUE}' < \"\$sql_file\"
    }

    cleanup() {
      $(after_each_profile_sql_down)
    }
    trap cleanup EXIT

    run_sql_file sql/task_persistence_pg/001_task_persistence_up.sql

    PYTHON_BIN='python3'
    if [ -x .venv/bin/python ]; then
      PYTHON_BIN='.venv/bin/python'
    fi

    TASK_PERSISTENCE_BACKEND='postgres' \
    TASK_QUEUE_BACKEND='${queue_backend}' \
    RABBITMQ_E2E_REQUIRED='${rabbit_required}' \
    DATABASE_URL='${DB_URL}' \
    TASK_REGISTRY_POSTGRES_DSN='${DB_URL}' \
    TASK_EVENTS_POSTGRES_DSN='${DB_URL}' \
    \"\${PYTHON_BIN}\" -m pytest ${pytest_target} -q -rA
  "

  echo "[profile:${profile_name}] passed"
}

run_profile "postgres-memory" "memory" "tests/test_tasks_submit.py" "false"
run_profile "postgres-rabbitmq" "rabbitmq" "tests/test_tasks_rabbitmq_e2e.py" "true"

echo "[matrix] all profiles passed"
