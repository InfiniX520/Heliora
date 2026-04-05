#!/usr/bin/env bash
set -uo pipefail

# Host-side helper: preflight checks for release window cutover readiness.
# Steps (configurable):
#   1) .env consistency check
#   2) VM SQL review pack
#   3) VM runtime matrix regression
#   4) VM cutover + rollback rehearsal

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE=".env"
PYTHON_BIN="${PYTHON_BIN:-}"
RUN_SQL_REVIEW=true
RUN_MATRIX=true
RUN_REHEARSAL=true

REPORT_DIR_DEFAULT="${BACKEND_DIR}/.release-reports"
REPORT_DIR="${REPORT_DIR:-${REPORT_DIR_DEFAULT}}"
REPORT_FILE=""

OVERALL_STATUS="PASS"
REPORT_STEPS=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/preflight_release_window_vm.sh [options]

Options:
  --env-file <path>         Env file path for consistency check (default: .env)
  --python-bin <path>       Python executable for env check
  --report-file <path>      Output markdown report path
  --skip-sql-review         Skip scripts/verify_task_persistence_pg_vm.sh
  --skip-matrix             Skip scripts/run_task_persistence_pg_matrix_vm.sh
  --skip-rehearsal          Skip scripts/rehearse_task_persistence_cutover_rollback_vm.sh
  --help                    Show help

Pass-through env vars:
  SSH_BIN, SSH_HOST, REMOTE_BACKEND_DIR, SSH_COPY_ID_BIN
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --env-file)
        ENV_FILE="$2"
        shift 2
        ;;
      --python-bin)
        PYTHON_BIN="$2"
        shift 2
        ;;
      --report-file)
        REPORT_FILE="$2"
        shift 2
        ;;
      --skip-sql-review)
        RUN_SQL_REVIEW=false
        shift
        ;;
      --skip-matrix)
        RUN_MATRIX=false
        shift
        ;;
      --skip-rehearsal)
        RUN_REHEARSAL=false
        shift
        ;;
      --help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown option: $1"
        usage
        exit 2
        ;;
    esac
  done
}

detect_python_bin() {
  local candidate

  is_python_usable() {
    local py_bin="$1"
    [[ -n "${py_bin}" ]] || return 1
    "${py_bin}" -c "import sys" >/dev/null 2>&1
  }

  if [[ -n "${PYTHON_BIN}" ]]; then
    if [[ -x "${PYTHON_BIN}" ]] && is_python_usable "${PYTHON_BIN}"; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    return 1
  fi

  for candidate in \
    "${BACKEND_DIR}/.venv/bin/python" \
    "${BACKEND_DIR}/.venv/Scripts/python.exe"
  do
    if [[ -x "${candidate}" ]] && is_python_usable "${candidate}"; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  # Common local Conda environment names for this project.
  for candidate in \
    "/e/Miniconda03/envs/Heliora/python.exe" \
    "/e/Miniconda3/envs/Heliora/python.exe" \
    "/c/Miniconda03/envs/Heliora/python.exe" \
    "/c/Miniconda3/envs/Heliora/python.exe"
  do
    if [[ -x "${candidate}" ]] && is_python_usable "${candidate}"; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  candidate="$(command -v python3 2>/dev/null || true)"
  if [[ -n "${candidate}" ]] && is_python_usable "${candidate}"; then
    printf '%s\n' "${candidate}"
    return 0
  fi

  candidate="$(command -v python 2>/dev/null || true)"
  if [[ -n "${candidate}" ]] && is_python_usable "${candidate}"; then
    printf '%s\n' "${candidate}"
    return 0
  fi

  return 1
}

append_step_report() {
  local step_name="$1"
  local status="$2"
  local duration="$3"
  REPORT_STEPS+="| ${step_name} | ${status} | ${duration}s |"$'\n'
}

run_step() {
  local step_name="$1"
  shift

  local started_at
  local ended_at
  local duration

  echo "[preflight] start: ${step_name}"
  started_at="$(date +%s)"

  if "$@"; then
    ended_at="$(date +%s)"
    duration="$((ended_at - started_at))"
    echo "[preflight] pass: ${step_name} (${duration}s)"
    append_step_report "${step_name}" "PASS" "${duration}"
    return 0
  fi

  ended_at="$(date +%s)"
  duration="$((ended_at - started_at))"
  echo "[preflight] fail: ${step_name} (${duration}s)"
  append_step_report "${step_name}" "FAIL" "${duration}"
  OVERALL_STATUS="FAIL"
  return 1
}

step_env_consistency() {
  "${PYTHON_BIN}" "${BACKEND_DIR}/scripts/validate_env_consistency.py" --env-file "${ENV_FILE}"
}

step_sql_review() {
  bash "${BACKEND_DIR}/scripts/verify_task_persistence_pg_vm.sh"
}

step_matrix() {
  bash "${BACKEND_DIR}/scripts/run_task_persistence_pg_matrix_vm.sh"
}

step_rehearsal() {
  bash "${BACKEND_DIR}/scripts/rehearse_task_persistence_cutover_rollback_vm.sh"
}

write_report() {
  local ended_iso

  ended_iso="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  mkdir -p "${REPORT_DIR}"

  if [[ -z "${REPORT_FILE}" ]]; then
    REPORT_FILE="${REPORT_DIR}/release_preflight_$(date +"%Y%m%d_%H%M%S").md"
  fi

  cat > "${REPORT_FILE}" <<EOF
# Release Window Preflight Report

- generated_at_utc: ${ended_iso}
- backend_dir: ${BACKEND_DIR}
- env_file: ${ENV_FILE}
- overall_status: ${OVERALL_STATUS}

## Step Results

| Step | Outcome | Duration |
| --- | --- | --- |
${REPORT_STEPS}

## Execution Flags

- run_sql_review: ${RUN_SQL_REVIEW}
- run_matrix: ${RUN_MATRIX}
- run_rehearsal: ${RUN_REHEARSAL}

## Notes

- This report is generated on host side and can be attached to release Go/No-Go review.
- Use together with project release execution checklist evidence section.
EOF

  echo "[preflight] report: ${REPORT_FILE}"
}

main() {
  parse_args "$@"
  cd "${BACKEND_DIR}"

  if ! PYTHON_BIN="$(detect_python_bin)"; then
    echo "python interpreter not found."
    echo "Set --python-bin or PYTHON_BIN explicitly."
    exit 1
  fi

  run_step "env consistency" step_env_consistency || true

  if [[ "${RUN_SQL_REVIEW}" == "true" ]]; then
    run_step "vm sql review" step_sql_review || true
  fi

  if [[ "${RUN_MATRIX}" == "true" ]]; then
    run_step "vm runtime matrix" step_matrix || true
  fi

  if [[ "${RUN_REHEARSAL}" == "true" ]]; then
    run_step "vm cutover rollback rehearsal" step_rehearsal || true
  fi

  write_report

  if [[ "${OVERALL_STATUS}" == "PASS" ]]; then
    echo "[preflight] all selected checks passed"
    exit 0
  fi

  echo "[preflight] one or more checks failed"
  exit 1
}

main "$@"
