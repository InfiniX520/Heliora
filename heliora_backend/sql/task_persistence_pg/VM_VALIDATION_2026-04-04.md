# Day-4 Task Persistence VM Validation Record (2026-04-04)

## 1. Objective

Validate the PostgreSQL task persistence review pack on VM end-to-end:

1. apply schema (`001_task_persistence_up.sql`)
2. run lightweight verification (`002_task_persistence_verify.sql`)
3. run expert assertion suite (`003_task_persistence_expert_review_suite.sql`)
4. rollback cleanup (`001_task_persistence_down.sql`)

## 2. Execution Environment

Host:

1. Windows PowerShell + Git Bash
2. SSH client: `E:/Git_A/Git/usr/bin/ssh.exe`
3. SSH alias: `Heliora-VM`

VM:

1. remote user: `heliora`
2. remote backend path: `/home/heliora/heliora_backend`
3. PostgreSQL runtime: Docker container `heliora-postgres`
4. VM does not provide host-side `psql` binary in PATH

## 3. Command Used

From host backend directory:

```bash
bash scripts/verify_task_persistence_pg_vm.sh
```

The script auto-selected:

1. remote backend path `/home/heliora/heliora_backend`
2. execution mode `docker exec into heliora-postgres` (fallback because `psql` missing on VM)

## 4. Result Summary

Overall status: PASS

Key checkpoints:

1. `[1/5] SSH and path ok` passed
2. `[2/5] execution mode: docker exec into heliora-postgres` selected
3. `[4/5] run SQL review pack` completed
4. `[5/5] done` reached
5. `Schema rolled back after verification.` confirmed

## 5. Verification Evidence (high-level)

`001_task_persistence_up.sql`:

1. table/function/trigger/index creation completed
2. comments and constraints applied

`002_task_persistence_verify.sql`:

1. normal lifecycle transitions passed
2. terminal-state guard passed (`failed -> retrying` rejected)
3. soft-delete and event checks passed
4. transaction ended with `ROLLBACK`

`003_task_persistence_expert_review_suite.sql`:

1. positive/negative assertions executed successfully
2. optimistic lock checks (conflict/success) passed
3. append-only and truncate guards passed
4. EXPLAIN plans showed expected indexes
5. transaction ended with `ROLLBACK`

`001_task_persistence_down.sql`:

1. indexes/tables/functions dropped cleanly
2. cleanup ended with `COMMIT`

## 6. Issues Encountered and Fixes

Issue A:

1. initial script could not auto-detect remote backend path
2. root cause: VM uses `/home/heliora/heliora_backend`
3. fix: added `~/heliora_backend` into detection candidates

Issue B:

1. VM had no `psql` in PATH
2. root cause: only containerized PostgreSQL runtime available
3. fix: script enhanced with docker fallback mode:
   - detect container `heliora-postgres`
   - execute SQL using `docker exec -i ... psql < file.sql`

## 7. Updated Assets

1. `scripts/verify_task_persistence_pg_vm.sh` (path detection + docker fallback)
2. `README.md` (VM validation section updated)
3. `sql/task_persistence_pg/README.md` (helper behavior updated)
4. this record file (`VM_VALIDATION_2026-04-04.md`)

## 8. Next Step

Proceed to runtime integration stage:

1. wire PostgreSQL task state/event stores into backend runtime
2. add PostgreSQL integration gate in CI
3. keep this VM script as the pre-merge DB validation baseline

## 9. Reboot Re-run Validation (2026-04-04)

After unexpected host restart, the same validation chain was executed again using:

```bash
bash scripts/verify_task_persistence_pg_vm.sh
```

Observed checkpoints:

1. `[1/5] SSH and path ok: /home/heliora/heliora_backend`
2. `[2/5] execution mode: docker exec into heliora-postgres`
3. `001_task_persistence_up.sql` applied successfully (tables/functions/triggers/indexes/comments)
4. `002_task_persistence_verify.sql` passed and ended with `ROLLBACK`
5. `003_task_persistence_expert_review_suite.sql` passed and ended with `ROLLBACK`
6. `001_task_persistence_down.sql` cleanup completed
7. final status: `Schema rolled back after verification.`

Conclusion:

1. VM verification workflow is restart-resilient.
2. SQL review pack remains deterministic under containerized PostgreSQL mode.

## 10. Runtime Integration Delta (same day)

First runtime integration step has been implemented in backend codebase:

1. task persistence now supports `sqlite/postgres` backend switch via `TASK_PERSISTENCE_BACKEND`.
2. both state store and event store can use PostgreSQL DSN (`*_POSTGRES_DSN` with fallback to `DATABASE_URL`).
3. default remains `sqlite` to preserve existing local/test behavior.

Changed files:

1. `app/core/config.py`
2. `app/services/task_state_store.py`
3. `app/services/task_event_store.py`
4. `.env.example`
5. `requirements.txt`
6. `README.md`

## 11. Day Tag Snapshot

This record maps to project milestone:

1. Day-4.1 completed: VM verification pipeline stabilized and runtime persistence backend switch (`sqlite/postgres`) landed.
2. Next target is Day-4.2: PostgreSQL runtime smoke and CI integration gate.

## 12. Day-4.2 Runtime Smoke (VM, PostgreSQL Backend)

Execution target:

1. run API-level task flow tests on PostgreSQL persistence backend (`submit/status/events/consume/cancel` path covered by `tests/test_tasks_submit.py`)
2. keep schema lifecycle deterministic (down -> up -> pytest -> down)

Run context:

1. backend path: `/home/heliora/heliora_backend`
2. PostgreSQL runtime: container `heliora-postgres`
3. test env: `TASK_PERSISTENCE_BACKEND=postgres`, `TASK_QUEUE_BACKEND=memory`, `DATABASE_URL=postgresql://heliora:heliora_pg_pass@127.0.0.1:5432/heliora`

Result:

1. first run exposed env drift (`TASK_QUEUE_BACKEND` inherited rabbitmq), causing consume-related assertions to fail.
2. fix applied: force `TASK_QUEUE_BACKEND=memory` for this smoke profile.
3. rerun passed: `tests/test_tasks_submit.py` -> `27 passed`.
4. post-run rollback succeeded via `001_task_persistence_down.sql`.

Output highlights:

1. pass set includes `test_consume_next_task_completes_and_updates_status`.
2. pass set includes retry/dead-letter related assertions.
3. pass set includes persistent fallback reads for task status/events.

Day-4.2 status impact:

1. PostgreSQL runtime smoke baseline is now executable and reproducible on VM.
2. CI workflow has been updated to include PostgreSQL service and this smoke gate.

## 13. Day-4.2 RabbitMQ + PostgreSQL Integration Regression (VM)

Execution target:

1. validate queue backend `rabbitmq` + persistence backend `postgres` in the same run profile.
2. ensure persistence write path is not silently degraded while API behavior still passes.

Run profile:

1. `TASK_PERSISTENCE_BACKEND=postgres`
2. `TASK_QUEUE_BACKEND=rabbitmq`
3. `RABBITMQ_E2E_REQUIRED=true`
4. `DATABASE_URL/TASK_REGISTRY_POSTGRES_DSN/TASK_EVENTS_POSTGRES_DSN` aligned to VM `.env` database URL.

Initial issues found:

1. VM venv missed `psycopg` dependency (resolved by reinstalling from `requirements.txt`).
2. first DSN used in command mismatched VM runtime password (resolved by reading VM `.env` `DATABASE_URL`).
3. hidden persistence errors were exposed during E2E:
   - events persisted before parent task row, causing foreign-key failures.
   - postgres upsert omitted `created_at`, triggering `updated_at < created_at` check violation.
   - teardown clear conflicted with append-only `task_events` policy.

Fixes applied:

1. task save/transition path reordered to persist state first, then append events.
2. postgres upsert now inserts both `created_at` and `updated_at` explicitly.
3. postgres clear path made governance-aware (safe skip on append-only/FK constrained clears).
4. RabbitMQ E2E test adds persistent-store assertions (`task_state_store` + `task_event_store`) to prevent memory-only false positives.

Final result:

1. VM regression passed: `tests/test_tasks_rabbitmq_e2e.py` -> `1 passed`.
2. schema cleanup (`001_down`) completed after run.
3. integration gate logic is ready for CI enforcement.

## 14. Post-fix Regression Matrix (VM)

After fixes in state/event persistence order, timestamp upsert, and clear behavior:

1. profile A (`TASK_PERSISTENCE_BACKEND=postgres`, `TASK_QUEUE_BACKEND=memory`):
   - command target: `tests/test_tasks_submit.py`
   - result: `27 passed`
2. profile B (`TASK_PERSISTENCE_BACKEND=postgres`, `TASK_QUEUE_BACKEND=rabbitmq`):
   - command target: `tests/test_tasks_rabbitmq_e2e.py`
   - result: `1 passed`
3. both profiles executed with schema lifecycle `001_up -> pytest -> 001_down` and cleanup completed successfully.

## 15. One-command runtime matrix helper (VM)

To reduce manual command drift, a host-side helper was added:

```bash
bash scripts/run_task_persistence_pg_matrix_vm.sh
```

Helper behavior:

1. checks SSH batch login and auto-detects `heliora_backend` path on VM.
2. reads VM `.env` `DATABASE_URL` and applies it to `DATABASE_URL/TASK_REGISTRY_POSTGRES_DSN/TASK_EVENTS_POSTGRES_DSN`.
3. runs profile A (`postgres + memory`) and profile B (`postgres + rabbitmq`) sequentially.
4. for each profile, executes `001_up -> pytest -> 001_down` automatically.

Execution result (2026-04-04):

1. profile A passed: `tests/test_tasks_submit.py` (`27 passed`).
2. profile B passed: `tests/test_tasks_rabbitmq_e2e.py` (`1 passed`).
3. matrix completed with final status: `all profiles passed`.

## 16. Day-4.3 cutover + rollback rehearsal (VM)

To validate migration safety, a new helper was executed:

```bash
bash scripts/rehearse_task_persistence_cutover_rollback_vm.sh
```

Execution flow:

1. run postgres cutover matrix (profiles A/B) via `run_task_persistence_pg_matrix_vm.sh`
2. run sqlite rollback validation (`TASK_PERSISTENCE_BACKEND=sqlite`, `TASK_QUEUE_BACKEND=memory`)

Observed result:

1. postgres profile A passed: `tests/test_tasks_submit.py` (`27 passed`)
2. postgres profile B passed: `tests/test_tasks_rabbitmq_e2e.py` (`1 passed`)
3. sqlite rollback validation passed: `tests/test_tasks_submit.py` (`27 passed`)
4. helper ended with `cutover and rollback rehearsal passed`

Impact:

1. migration rehearsal is now executable with one command.
2. rollback path is validated with the same baseline suite and can be reused before release windows.

## 17. Environment consistency preflight hardening (Day-4.3)

Goal:

1. prevent runtime regressions caused by env credential drift (`DATABASE_URL` vs `POSTGRES_*`, `RABBITMQ_URL` vs `RABBITMQ_DEFAULT_*`).

Changes:

1. added script: `scripts/validate_env_consistency.py`.
2. added CI gate: `python scripts/validate_env_consistency.py --env-file .env`.
3. added VM matrix preflight in `run_task_persistence_pg_matrix_vm.sh`.

Validation notes:

1. first local run exposed a false-positive on RabbitMQ default vhost `/`; parser was fixed for vhost compatibility.
2. local re-run passed.
3. VM matrix re-run shows preflight pass banner and both profiles pass as expected.

Result:

1. env consistency is now checked before runtime matrix execution and in CI.
2. DSN/password drift is caught earlier, before expensive integration tests.

## 18. Day-4.3 governance addendum (2026-04-05)

1. CI report hardening has been added:
   - pytest gates export JUnit XML reports
   - coverage gate exports coverage XML
   - workflow uploads `backend-rabbitmq-gate-reports` artifact
   - workflow writes gate outcomes to GitHub Step Summary
2. Release execution governance has been documented in:
   - `项目设计/05-实施与交付/05-发布窗口切流执行单.md`
3. This record remains the runtime verification evidence source; release window decisions must reference both this file and the cutover runbook.
