# Heliora Backend Scaffold

This directory contains the initial backend skeleton for Heliora.

## Path Portability Policy

1. Backend code must avoid hard-coded machine paths.
2. Runtime settings now resolve `.env` from backend root automatically.
3. You can run from any current directory as long as the Python environment is configured.

## Quick Start

### Python Version Policy

1. Preferred: Python 3.11 (long-term stable baseline).
2. Accepted now: Python 3.12 (Ubuntu 24.04 default).
3. Do not install project deps into system Python directly.

1. Create virtual environment:
   - python3 -m venv .venv
2. Activate virtual environment:
   - Linux/macOS: source .venv/bin/activate
   - Windows PowerShell: .venv\Scripts\Activate.ps1
3. Install dependencies:
   - pip install -r requirements.txt
4. Copy environment file:
   - cp .env.example .env
   - If `.env` already exists, keep your current values and sync missing keys from `.env.example`.
5. Start infrastructure services:
   - docker compose up -d
6. Run API:
   - python main.py

### Fast Bootstrap (recommended)

```bash
bash scripts/bootstrap_dev.sh
source .venv/bin/activate
python main.py
```

In another terminal:

```bash
bash scripts/smoke_api.sh
```

### Reboot Recovery (background mode)

After VM reboot, API process is not persistent by default. Use:

```bash
chmod +x scripts/start_api_bg.sh scripts/stop_api.sh
bash scripts/start_api_bg.sh
curl http://127.0.0.1:8000/health
```

By default, `start_api_bg.sh` now also starts background worker.

Stop API when needed:

```bash
bash scripts/stop_api.sh
```

Start/stop worker separately when needed:

```bash
bash scripts/start_worker_bg.sh
bash scripts/stop_worker.sh
```

### Common Errors and Fixes

1. `python: command not found`
   - Reason: system has `python3`, not `python`, and venv is not activated.
   - Fix:
     - `python3 -m venv .venv`
     - `source .venv/bin/activate`
     - `python -V`

2. `pytest: command not found`
   - Reason: dependencies not installed in virtual environment.
   - Fix:
     - `source .venv/bin/activate`
     - `pip install -r requirements.txt`
     - `pytest`

3. `/health: No such file or directory`
   - Reason: `/health` is HTTP path, not shell command.
   - Fix:
     - Start API: `python main.py`
     - Check in VM: `curl http://127.0.0.1:8000/health`
     - Check from Windows host (NAT forward): `http://127.0.0.1:8081/health`

4. `SettingsError: error parsing value for field "cors_origins"`
    - Reason: invalid CORS format in `.env`.
    - Supported values now:
       - Comma-separated: `CORS_ORIGINS=http://localhost:3000,http://localhost:5173`
       - JSON array: `CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]`

### Optional: switch to Python 3.11 on Ubuntu 24.04

If you need strict 3.11 locally, run:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install -r requirements.txt
```

## Available Endpoints

- GET /health
- POST /api/v1/chat
- POST /api/v1/memory/retrieve
- POST /api/v1/tasks/submit
- GET /api/v1/tasks/{task_id}
- GET /api/v1/tasks/{task_id}/events
- POST /api/v1/tasks/{task_id}/cancel
- POST /api/v1/tasks/consume-next

## Chat Endpoint Behavior (Day-1)

POST /api/v1/chat now provides a minimal deterministic flow:

1. Trims input content and rejects blank payload after trimming.
2. Enforces max content length by CHAT_MAX_CONTENT_CHARS.
3. Detects coarse intent (task_planning, memory_recall, status_check, general_chat).
4. Returns suggested next actions and turn_index for the session.

Failure codes:

1. INVALID_ARGUMENT: content is blank after trimming.
2. CONTENT_TOO_LONG: content length exceeds CHAT_MAX_CONTENT_CHARS.

## Memory Retrieve Behavior (Day-1)

POST /api/v1/memory/retrieve now provides a minimal deterministic retrieval flow:

1. Trims query and rejects blank payload after trimming.
2. Enforces max query length by MEMORY_MAX_QUERY_CHARS.
3. Uses a rule-based in-memory store with token scoring and scope filtering.
4. Returns ranked memories plus injected_context for downstream prompt usage.

Failure codes:

1. FORBIDDEN: memory service is disabled.
2. INVALID_ARGUMENT: query is blank after trimming.
3. QUERY_TOO_LONG: query length exceeds MEMORY_MAX_QUERY_CHARS.

## Task Queue Backend Mode (Day-2.5)

Task queue now supports backend switching by configuration:

1. TASK_QUEUE_BACKEND=memory
   - Default mode, fully in-process, easiest for local debugging.
2. TASK_QUEUE_BACKEND=rabbitmq
   - Uses RabbitMQ queues for submit/consume operations.
   - If TASK_QUEUE_FAIL_OPEN=true, only recoverable RabbitMQ connection/channel failures auto-fallback to memory backend.

Related settings:

1. RABBITMQ_URL: RabbitMQ connection string.
2. TASK_QUEUE_SLA_P0_MS: SLA ms for realtime P0 tasks.
3. TASK_QUEUE_SLA_P1_MS: SLA ms for realtime P1 tasks.
4. TASK_QUEUE_SLA_P2_MS: SLA ms for normal P2 tasks.
5. TASK_QUEUE_SLA_P3_MS: SLA ms for batch P3 tasks.
6. TASK_QUEUE_SLA_MEMORY_MS: SLA ms for memory-routed tasks.
7. TASK_RETRY_MAX_ATTEMPTS: max retries before dead-lettering.
8. TASK_RETRY_BASE_DELAY_SECONDS: retry base delay.
9. TASK_RETRY_MAX_DELAY_SECONDS: retry delay upper bound.
10. TASK_RETRY_BACKOFF_FACTOR: exponential factor.
11. TASK_QUEUE_FAIL_OPEN: whether to fallback to memory when RabbitMQ is unavailable.

Routing policy:

1. Queue selection and SLA mapping now live in service module `app/services/task_routing.py`.
2. API endpoint only consumes routing result to keep layer boundaries clearer.

## Task Lifecycle Behavior (Day-3.4 Alignment)

Task lifecycle now supports a minimal queue-consumer loop:

1. Submit task emits created/routed/queued audit events.
2. Consume endpoint picks one queued task (optionally by queue).
3. Worker transitions task through running -> retrying -> running -> completed/failed.
4. Failed tasks are requeued with exponential backoff until TASK_RETRY_MAX_ATTEMPTS.
5. RabbitMQ retry path uses TTL + dead-letter strategy (non-blocking worker).
6. After max attempts, failed tasks are sent to dead-letter queue.
7. Cancel endpoint transitions task to canceled and worker skips terminal tasks.
8. Events endpoint returns full audit trail for troubleshooting.
9. Task transitions are guarded by an allowed-transition state machine; invalid transitions are rejected.

Failure behavior:

1. consume-next returns code=NOOP when no queued task is available or task is terminal/canceled.
2. forced failure path returns status=retrying before max attempts, then status=failed at max attempts.
3. retrying/failed event metadata includes action=requeued or action=dead_lettered.
4. retry metadata includes retry_delay_seconds (and next_retry_at for in-memory backend).
5. Invalid task status transitions now fail with code=TASK_TRANSITION_INVALID.

## Task Events Persistence (Day-3.3)

1. Task events persistence supports backend switch: `sqlite` or `postgres`.
2. Default backend: `TASK_PERSISTENCE_BACKEND=sqlite`.
3. SQLite path: `TASK_EVENTS_SQLITE_PATH=.data/task_events.db`.
4. PostgreSQL DSN: `TASK_EVENTS_POSTGRES_DSN` (falls back to `DATABASE_URL` if empty).
5. Endpoint `/api/v1/tasks/{task_id}/events` can read from persistent store when task is no longer in memory.
6. Events query filters `start_ts` and `end_ts` now require valid ISO-8601 datetimes and are normalized to UTC.

Related settings:

1. TASK_PERSISTENCE_BACKEND=sqlite|postgres
2. TASK_EVENTS_PERSISTENCE_ENABLED=true|false
3. TASK_EVENTS_SQLITE_PATH=.data/task_events.db
4. TASK_EVENTS_POSTGRES_DSN=postgresql://... (optional)
5. DATABASE_URL=postgresql://... (fallback DSN)

## Task Registry Persistence (Day-3.6)

1. Task status persistence supports backend switch: `sqlite` or `postgres`.
2. Default backend: `TASK_PERSISTENCE_BACKEND=sqlite`.
3. SQLite path: `TASK_REGISTRY_SQLITE_PATH=.data/task_registry.db`.
4. PostgreSQL DSN: `TASK_REGISTRY_POSTGRES_DSN` (falls back to `DATABASE_URL` if empty).
5. Endpoint `/api/v1/tasks/{task_id}` can read from persistent task registry when in-memory cache is missing.

Related settings:

1. TASK_PERSISTENCE_BACKEND=sqlite|postgres
2. TASK_REGISTRY_PERSISTENCE_ENABLED=true|false
3. TASK_REGISTRY_SQLITE_PATH=.data/task_registry.db
4. TASK_REGISTRY_POSTGRES_DSN=postgresql://... (optional)
5. DATABASE_URL=postgresql://... (fallback DSN)

## Day-3 Worker Mode (continuous consumption)

1. A standalone background worker daemon continuously calls consume-next.
2. Start API script can auto-start worker to avoid manual consume calls.
3. Worker PID/log files:
   - `.worker.pid`
   - `.worker.log`
4. Worker behavior can be tuned with env keys:
   - TASK_WORKER_API_BASE_URL
   - TASK_WORKER_QUEUE
   - TASK_WORKER_IDLE_SECONDS
   - TASK_WORKER_BUSY_SECONDS
   - TASK_WORKER_ERROR_BACKOFF_SECONDS
   - TASK_WORKER_LOG_LEVEL
5. Worker now loads `.env` using Python parser (not shell `source`) to avoid CRLF/space parsing failures.

## RabbitMQ Retry Smoke Script (Day-3.3)

Use this script to verify retry and dead-letter behavior:

```bash
bash scripts/smoke_rabbitmq_retry.sh
```

Recommended before running:

1. Set `TASK_QUEUE_BACKEND=rabbitmq` in `.env`.
2. Restart API and worker: `bash scripts/stop_api.sh && bash scripts/start_api_bg.sh`.
3. The script auto-resolves Python interpreter in this order: `.venv/bin/python` -> `python3` -> `python`.
4. The script preflights runtime dependencies and RabbitMQ connectivity (checks `pika` import and opens a test AMQP connection).
5. The script requires failed-event metadata `backend=rabbitmq`; if fail-open fallback switches to memory backend, smoke test exits with failure and prints `fallback_reason` when available.

## Task Persistence SQL VM Verification (Day-4)

Use host-side helper to run PostgreSQL task persistence review pack on VM over SSH:

```bash
bash scripts/verify_task_persistence_pg_vm.sh
```

Notes:

1. Requires SSH host alias `Heliora-VM` in `~/.ssh/config`.
2. SSH client path is now auto-detected by helper scripts (`command -v ssh` first, then common Git for Windows paths).
3. You can still override SSH binary explicitly when needed: `SSH_BIN=/path/to/ssh bash scripts/verify_task_persistence_pg_vm.sh`.
4. Default VM auth assumes key-based login; if not configured, follow script output and run `ssh-copy-id` once.
5. The script auto-detects remote backend path and supports `~/heliora_backend`.
6. If `psql` is unavailable on VM, script automatically falls back to `docker exec` on container `heliora-postgres`.
7. The script runs `001_up` + `002_verify` + `003_expert_review_suite` and rolls back via `001_down` by default.
8. Set `KEEP_SCHEMA=true` to keep schema after verification.
9. Override remote path when needed: `REMOTE_BACKEND_DIR=/path/to/heliora_backend bash scripts/verify_task_persistence_pg_vm.sh`.

Runtime regression matrix helper (Day-4.2):

```bash
bash scripts/run_task_persistence_pg_matrix_vm.sh
```

The matrix helper runs two runtime profiles on VM:

1. `TASK_PERSISTENCE_BACKEND=postgres` + `TASK_QUEUE_BACKEND=memory` -> `tests/test_tasks_submit.py`
2. `TASK_PERSISTENCE_BACKEND=postgres` + `TASK_QUEUE_BACKEND=rabbitmq` -> `tests/test_tasks_rabbitmq_e2e.py`

For each profile, it executes `001_up -> pytest -> 001_down` automatically.

Before running profile tests, the helper executes env consistency preflight:

```bash
python scripts/validate_env_consistency.py --env-file .env
```

This catches DSN/password/user drift early.

Cutover + rollback rehearsal helper (Day-4.3):

```bash
bash scripts/rehearse_task_persistence_cutover_rollback_vm.sh
```

This helper executes:

1. postgres cutover matrix (`postgres+memory` and `postgres+rabbitmq`)
2. sqlite rollback validation (`TASK_PERSISTENCE_BACKEND=sqlite`, `TASK_QUEUE_BACKEND=memory`)

The goal is to verify that both cutover and rollback paths remain executable on VM.

Release-window preflight helper (Day-4.4):

```bash
bash scripts/preflight_release_window_vm.sh
```

This helper orchestrates pre-release checks and emits a markdown report:

1. env consistency (`scripts/validate_env_consistency.py`)
2. VM SQL review (`scripts/verify_task_persistence_pg_vm.sh`)
3. VM runtime matrix (`scripts/run_task_persistence_pg_matrix_vm.sh`)
4. VM cutover + rollback rehearsal (`scripts/rehearse_task_persistence_cutover_rollback_vm.sh`)

Default report output:

1. `.release-reports/release_preflight_YYYYMMDD_HHMMSS.md`

Quick smoke mode (skip heavy VM steps):

```bash
bash scripts/preflight_release_window_vm.sh \
   --skip-sql-review \
   --skip-matrix \
   --skip-rehearsal
```

Portability update (Day-4.4):

1. `scripts/verify_task_persistence_pg_vm.sh`
2. `scripts/run_task_persistence_pg_matrix_vm.sh`
3. `scripts/rehearse_task_persistence_cutover_rollback_vm.sh`

All three VM helpers now remove host-specific absolute SSH defaults and use a shared auto-discovery strategy with environment override support.

## CI RabbitMQ Gate (Day-3.9)

1. Workflow path: `.github/workflows/backend-rabbitmq-gate.yml`.
2. CI provides RabbitMQ service and PostgreSQL service in the same workflow.
3. CI runs PostgreSQL task persistence smoke gate first:
   - applies `sql/task_persistence_pg/001_task_persistence_up.sql`
   - runs `tests/test_tasks_submit.py` with `TASK_PERSISTENCE_BACKEND=postgres` and `TASK_QUEUE_BACKEND=memory`
   - rolls back with `sql/task_persistence_pg/001_task_persistence_down.sql`
4. CI runs baseline RabbitMQ E2E gate: `tests/test_tasks_rabbitmq_e2e.py`.
5. CI runs RabbitMQ + PostgreSQL integration gate:
   - applies `sql/task_persistence_pg/001_task_persistence_up.sql`
   - runs `tests/test_tasks_rabbitmq_e2e.py` with `TASK_PERSISTENCE_BACKEND=postgres` and `TASK_QUEUE_BACKEND=rabbitmq`
   - rolls back with `sql/task_persistence_pg/001_task_persistence_down.sql`
6. CI sets `RABBITMQ_E2E_REQUIRED=true`; when RabbitMQ is unavailable, E2E test fails instead of skip.
7. CI runs env consistency gate: `python scripts/validate_env_consistency.py --env-file .env`.
8. CI runs `python -m ruff check app tests` as lint gate.
9. CI runs `python -m mypy app` as type-check gate.
10. CI runs `python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=70 -q` as coverage gate.
11. CI exports JUnit reports and coverage xml into `.ci-reports/`.
12. CI uploads `.ci-reports/` as artifact `backend-rabbitmq-gate-reports`.
13. CI writes a gate outcome table into GitHub job summary for reviewer traceability.
14. CI runs ANN audit in non-blocking mode: `python -m ruff check app tests scripts --select ANN` and stores output in `.ci-reports/ann_audit.txt`.
15. Any blocking gate failure still blocks the workflow.
