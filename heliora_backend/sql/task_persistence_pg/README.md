# Task Persistence SQL Design (PostgreSQL)

This folder is the Day-4 expert review pack for task persistence migration.

## Scope

Current scope includes two tables only:

1. task_registry
2. task_events

Reason:

1. Current execution stage is SQLite -> PostgreSQL for task persistence.
2. Memory-domain tables are reviewed in a separate package.

## Recommended reading order for experts

1. JUDGE_DETAILED_EXPLANATION.md
2. EXPERT_DESIGN_REVIEW.md
3. 001_task_persistence_up.sql
4. 003_task_persistence_expert_review_suite.sql
5. 002_task_persistence_verify.sql
6. 001_task_persistence_down.sql

## Files and purpose

1. 001_task_persistence_up.sql
   - schema creation (tables, constraints, triggers, indexes, comments)
2. 001_task_persistence_down.sql
   - rollback script
3. 002_task_persistence_verify.sql
   - lightweight verify script with transaction rollback
4. 003_task_persistence_expert_review_suite.sql
   - assertion-style expert suite (positive/negative checks + explain plans)
5. EXPERT_DESIGN_REVIEW.md
   - requirement traceability, data dictionary, consistency model, risk boundaries
6. JUDGE_DETAILED_EXPLANATION.md
   - single-document package for judges (background, design, verification, alignment status)

## How to run review scripts

Use psql with your PostgreSQL connection:

```bash
psql "$DATABASE_URL" -f sql/task_persistence_pg/001_task_persistence_up.sql
psql "$DATABASE_URL" -f sql/task_persistence_pg/002_task_persistence_verify.sql
psql "$DATABASE_URL" -f sql/task_persistence_pg/003_task_persistence_expert_review_suite.sql
```

Rollback:

```bash
psql "$DATABASE_URL" -f sql/task_persistence_pg/001_task_persistence_down.sql
```

Host-side VM helper (recommended for local Windows + VM workflow):

```bash
bash scripts/verify_task_persistence_pg_vm.sh
```

The helper script:

1. checks SSH batch login for `Heliora-VM`.
2. auto-detects remote `heliora_backend` directory (including `~/heliora_backend`; or use `REMOTE_BACKEND_DIR`).
3. uses VM `psql` when available; otherwise falls back to `docker exec` on `heliora-postgres`.
4. runs `001_up` + `002_verify` + `003_expert_review_suite`.
5. runs `001_down` by default unless `KEEP_SCHEMA=true`.

## Security notes

1. `payload_json` and `metadata_json` are schema-validated as JSON objects, but should not store plaintext secrets/tokens.
2. If sensitive data is unavoidable, encrypt or redact at application layer before write.
3. `task_events` is append-only by trigger policy (no UPDATE/DELETE/TRUNCATE) to preserve audit integrity.

## Lifecycle and soft-delete notes

1. State machine is aligned to unified baseline: `created -> routed -> queued -> running -> completed`, `created -> routed -> queued -> running -> retrying -> running`, `running -> failed`, `queued/running -> canceled`.
2. `failed` is terminal; retry must happen before entering `failed`.
3. Parent hard-delete is restricted to protect event audit history.
4. For consistency-critical writes, prefer `app_task_transition_with_event(...)` to update status and insert event in one transaction.
5. `deleted_at` is an optional storage-layer governance field for active-list visibility control and is not required in TaskStatus API payload at this stage.

## Backfill notes

1. On INSERT, `created_at`/`updated_at`/`version` use DB defaults when omitted.
2. For controlled historical imports, explicit values for those fields are preserved.
3. Guardrails are enforced: future timestamps are rejected, and `updated_at` cannot be earlier than `created_at`.

## Index notes

1. `idx_task_registry_active_status_updated_at` serves active-task hot path queries.
2. `idx_task_registry_status_updated_at` is kept for all-row status queries (including soft-deleted rows).

## Atomic transition example

```sql
SELECT app_task_transition_with_event(
   'task_demo_001',
   'running',
   'evt_demo_001',
   'running',
   'worker picked task',
   '{"queue":"normal.queue"}'::jsonb,
   'worker_daemon',
   NULL,
   'trc_demo_001'
);
```

Permission note:

1. `app_task_transition_with_event(...)` uses invoker privileges.
2. Caller must have permission to `UPDATE task_registry` and `INSERT task_events`.

## Review outcome expectation

1. Experts can evaluate lifecycle correctness without runtime code.
2. Experts can verify data governance fields (operator/error_code/trace_id).
3. Experts can inspect index strategy through explain outputs.
4. Scripts are non-destructive in verify phases because they end with ROLLBACK.
