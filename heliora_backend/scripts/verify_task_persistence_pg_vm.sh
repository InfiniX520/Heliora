#!/usr/bin/env bash
set -euo pipefail

# Host-side helper: run PostgreSQL task persistence review SQL on VM over SSH.
SSH_BIN="${SSH_BIN:-}"
SSH_COPY_ID_BIN="${SSH_COPY_ID_BIN:-}"
SSH_HOST="${SSH_HOST:-Heliora-VM}"
REMOTE_BACKEND_DIR="${REMOTE_BACKEND_DIR:-}"

PGHOST_VALUE="${PGHOST_VALUE:-127.0.0.1}"
PGPORT_VALUE="${PGPORT_VALUE:-5432}"
PGUSER_VALUE="${PGUSER_VALUE:-heliora}"
PGDATABASE_VALUE="${PGDATABASE_VALUE:-heliora}"
PGPASSWORD_VALUE="${PGPASSWORD_VALUE:-heliora_pg_pass}"
KEEP_SCHEMA="${KEEP_SCHEMA:-false}"

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

detect_ssh_copy_id_bin() {
  local candidate

  candidate="$(command -v ssh-copy-id 2>/dev/null || true)"
  if [[ -n "${candidate}" ]]; then
    printf '%s\n' "${candidate}"
    return 0
  fi

  for candidate in \
    "/e/Git_A/Git/usr/bin/ssh-copy-id" \
    "/e/Git_A/Git/bin/ssh-copy-id"
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

if [[ -z "${SSH_COPY_ID_BIN}" ]]; then
  SSH_COPY_ID_BIN="$(detect_ssh_copy_id_bin || true)"
fi
if [[ -z "${SSH_COPY_ID_BIN}" ]]; then
  SSH_COPY_ID_BIN="ssh-copy-id"
fi

ssh_exec() {
  "${SSH_BIN}" -F "${HOME}/.ssh/config" "$@"
}

if ! ssh_exec -o BatchMode=yes "${SSH_HOST}" "echo connected" >/dev/null 2>&1; then
  echo "Cannot login to ${SSH_HOST} in batch mode."
  echo "Run this once to install local public key, then rerun:"
  echo "  ${SSH_COPY_ID_BIN} -i ~/.ssh/id_ed25519_heliora_vm.pub -p 2026 heliora@127.0.0.1"
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

echo "[1/5] SSH and path ok: ${REMOTE_BACKEND_DIR}"

EXEC_MODE=""
if ssh_exec "${SSH_HOST}" "command -v psql >/dev/null 2>&1"; then
  EXEC_MODE="psql"
  echo "[2/5] execution mode: psql on VM"
elif ssh_exec "${SSH_HOST}" "docker ps --format '{{.Names}}' | grep -qx 'heliora-postgres'"; then
  EXEC_MODE="docker"
  echo "[2/5] execution mode: docker exec into heliora-postgres"
else
  echo "Neither 'psql' nor docker container 'heliora-postgres' is available on VM."
  exit 1
fi

if ssh_exec "${SSH_HOST}" "test -d \"\$HOME/heliora-infra\""; then
  echo "[3/5] infra status"
  ssh_exec "${SSH_HOST}" "cd \"\$HOME/heliora-infra\"; docker compose ps"
else
  echo "[3/5] skip infra status (~/heliora-infra not found)"
fi

echo "[4/5] run SQL review pack"
if [[ "${EXEC_MODE}" == "psql" ]]; then
  ssh_exec "${SSH_HOST}" "
    set -euo pipefail
    cd \"${REMOTE_BACKEND_DIR}\"
    export PGPASSWORD='${PGPASSWORD_VALUE}'
    export PGHOST='${PGHOST_VALUE}'
    export PGPORT='${PGPORT_VALUE}'
    export PGUSER='${PGUSER_VALUE}'
    export PGDATABASE='${PGDATABASE_VALUE}'
    psql -v ON_ERROR_STOP=1 -f sql/task_persistence_pg/001_task_persistence_up.sql
    psql -v ON_ERROR_STOP=1 -f sql/task_persistence_pg/002_task_persistence_verify.sql
    psql -v ON_ERROR_STOP=1 -f sql/task_persistence_pg/003_task_persistence_expert_review_suite.sql
    if [[ '${KEEP_SCHEMA}' != 'true' ]]; then
      psql -v ON_ERROR_STOP=1 -f sql/task_persistence_pg/001_task_persistence_down.sql
    fi
  "
else
  ssh_exec "${SSH_HOST}" "
    set -euo pipefail
    cd \"${REMOTE_BACKEND_DIR}\"
    run_sql_file() {
      local sql_file=\"\$1\"
      docker exec -i \\
        -e PGPASSWORD='${PGPASSWORD_VALUE}' \\
        heliora-postgres \\
        psql -v ON_ERROR_STOP=1 -U '${PGUSER_VALUE}' -d '${PGDATABASE_VALUE}' < \"\$sql_file\"
    }
    run_sql_file sql/task_persistence_pg/001_task_persistence_up.sql
    run_sql_file sql/task_persistence_pg/002_task_persistence_verify.sql
    run_sql_file sql/task_persistence_pg/003_task_persistence_expert_review_suite.sql
    if [[ '${KEEP_SCHEMA}' != 'true' ]]; then
      run_sql_file sql/task_persistence_pg/001_task_persistence_down.sql
    fi
  "
fi

echo "[5/5] done"
if [[ "${KEEP_SCHEMA}" == "true" ]]; then
  echo "Schema kept on VM (KEEP_SCHEMA=true)."
else
  echo "Schema rolled back after verification."
fi
