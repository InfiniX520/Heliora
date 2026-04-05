# Task Persistence PostgreSQL Design Review Pack

## 1. Review objective

This document explains design quality for external experts, not only implementation details.

Review scope:

1. task persistence domain only
2. tables in this stage: task_registry + task_events
3. migration stage: SQLite -> PostgreSQL for Day-4

Out of scope:

1. memory-domain tables (reviewed in separate pack)
2. runtime code switch and production rollout scripts

## 2. Requirement traceability

Design requirements mapped to schema constraints:

1. Task status lifecycle must be controlled by state machine.
   - Implemented by status check constraints + transition trigger.
2. Task timeline must be auditable and queryable.
   - Implemented by immutable event table + indexes on task_id/event_type/trace_id/ts.
3. Every persisted row must be parse-safe.
   - Implemented by JSONB object checks for payload_json and metadata_json.
4. Event lookup must support troubleshooting quickly.
   - Implemented by timeline and trace indexes.
5. Updates should be conflict-aware for future optimistic controls.
   - Implemented by monotonic version column.
6. Storage-layer active listing should support optional soft-deletion control without destroying audit records.
   - Implemented by deleted_at marker + active partial index; this is a DB-layer governance field and is not required in TaskStatus API payload for this stage.
7. Status update and lifecycle event write should support one-step atomic path.
   - Implemented by app_task_transition_with_event function.

## 3. Table-by-table mission definition

### 3.1 task_registry mission

Functional mission:

1. Single source of truth for latest task state.
2. Supports GET status endpoint directly.
3. Rejects invalid lifecycle transitions.

Governance mission:

1. Preserves created_at and auto-updates updated_at.
2. Tracks row mutation count using version.
3. Maintains payload snapshot compatibility.
4. Supports soft-delete visibility control by deleted_at.
5. Provides optional DB-level atomic transition API for consistency-critical write paths.

### 3.2 task_events mission

Functional mission:

1. Stores immutable lifecycle timeline.
2. Supports events filtering by task_id/event_type/time window.
3. Supports trace correlation across services.

Governance mission:

1. Captures operator and error_code for accountability.
2. Enforces status vocabulary consistency.
3. Keeps metadata parse-safe with JSON object constraint.

## 4. Lifecycle correctness model

Allowed status transitions:

1. created -> routed
2. routed -> queued
3. queued -> running, canceled
4. running -> retrying, completed, failed, canceled
5. retrying -> running

Terminal states:

1. completed
2. failed
3. canceled

Design note:

1. failed is terminal in this stage; retries must occur before entering failed.
2. same-status update is allowed to support payload patching without state change.
3. soft-deleted rows (deleted_at is not null) reject status transitions.


## 5. Data dictionary (expert quick view)

### 5.1 task_registry fields

1. task_id: business key, primary key.
2. status: controlled lifecycle status.
3. payload_json: full snapshot object for compatibility.
4. created_at: immutable creation timestamp; DB default is applied when omitted on insert, explicit historical value is allowed for controlled backfill.
5. updated_at: mutable last-write timestamp; defaults to created_at on insert when omitted.
6. deleted_at: soft-delete marker; null means active.
7. version: monotonic counter for optimistic controls; defaults to 1 on insert when omitted.

### 5.2 task_events fields

1. event_id: business unique idempotent key.
2. task_id: parent task reference.
3. event_type: semantic event label.
4. from_status/to_status: transition edge.
5. message: operator-facing event message.
6. metadata_json: structured event context.
7. operator: actor identity.
8. error_code: business/system failure code.
9. trace_id: distributed tracing correlation id.
10. ts: event timestamp.

## 6. Query patterns and index strategy

Pattern A: list tasks by status and recency

1. query: where deleted_at is null and status = ? order by updated_at desc limit N
2. index: idx_task_registry_active_status_updated_at

Pattern A-Compat: list all tasks (including soft-deleted) by status

1. query: where status = ? order by updated_at desc limit N
2. index: idx_task_registry_status_updated_at

Design note:

1. Keeping both active-only and full-table status indexes intentionally preserves predictable plans for both query classes.

Pattern B: fetch one task timeline

1. query: where task_id = ? order by ts asc
2. index: PRIMARY KEY (task_id, ts, event_id) with left-prefix coverage

Pattern C: investigate one trace across tasks

1. query: where trace_id = ? order by ts desc
2. index: idx_task_events_trace_id_ts (partial, not null)

Pattern D: monitor one event type trend

1. query: where event_type = ? order by ts desc
2. index: idx_task_events_event_type_ts

Pattern E: investigate by operator attribution (FIX-07)

1. query: where operator = ? order by ts desc
2. index: idx_task_events_operator_ts (partial, not null)

Pattern F: error analysis by error code (FIX-10)

1. query: where error_code = ? order by ts desc
2. index: idx_task_events_error_code_ts (partial, not null)

Pattern G: list recently created tasks (FIX-10)

1. query: where deleted_at is null order by created_at desc limit N
2. index: idx_task_registry_active_created_at (partial, deleted_at is null)

## 7. Consistency and failure semantics

Consistency model:

1. status integrity is strongly enforced by DB trigger.
2. event-parent relationship is strongly enforced by FK.
3. payload and metadata shape are strongly enforced by JSON object checks.
4. task_events is append-only, enforced by BEFORE UPDATE/DELETE trigger.
5. key identity fields are protected by non-blank CHECK constraints.
6. app_task_transition_with_event offers one-transaction update+event insertion for stronger cross-table consistency.

Failure semantics:

1. invalid status transition raises check_violation.
2. duplicate event_id raises unique_violation.
3. non-object metadata/payload raises check_violation.
4. update/delete on task_events raises check_violation.
5. truncate on task_events raises check_violation.

## 8. Security and governance considerations

1. No dynamic SQL in schema scripts.
2. JSON constraints prevent malformed payload shape drift.
3. operator/error_code/trace_id fields support post-incident accountability.
4. ON DELETE RESTRICT prevents parent hard-delete from erasing audit trail.
5. append-only trigger reduces audit tampering risk in shared DB environments.
6. payload_json should not store plaintext secrets/tokens; encrypt or redact in application layer when needed. **(FIX-10: Enhanced security notes in table comments)**
7. task_events TRUNCATE is blocked by trigger-level policy.
8. app_task_transition_with_event runs with invoker privileges and requires explicit caller permissions.
9. All trigger functions have `SET search_path = pg_catalog, public` to prevent search_path hijacking (FIX-01).
10. **Connection management**: See FIX-11 for connection pooling and timeout recommendations to prevent resource exhaustion.

## 9. Migration and rollout plan (design level)

Phase 1: review

1. run up script
2. run verify script
3. run expert suite

Phase 2: runtime integration

1. add PostgreSQL store implementation
2. add switch by config (read/write path)
3. keep SQLite fallback for local/dev transition window
4. route consistency-critical lifecycle writes through app_task_transition_with_event

Phase 3: cutover

1. enable dual-write in staging
2. compare row counts and timeline consistency
3. switch reads to PostgreSQL

## 10. Verification pack and success criteria

Files:

1. 001_task_persistence_up.sql
2. 001_task_persistence_down.sql
3. 002_task_persistence_verify.sql
4. 003_task_persistence_expert_review_suite.sql

Success criteria:

1. all positive lifecycle transitions pass.
2. invalid transitions are rejected.
3. duplicate event_id is rejected.
4. metadata shape constraints work.
5. payload_json non-object writes are rejected.
6. task_events update/delete is rejected.
7. explain plans show target index usage on key paths.
8. app_task_transition_with_event writes both status and event consistently.
9. task_events truncate is rejected.

## 11. Additional fixes from round-3 deep review

### FIX-10. Security hardening: sensitive field storage policy and index optimization

**Issues found**:
1. Table-level security notes were insufficient for sensitive field handling
2. Missing indexes for common query patterns (created_at pagination, error_code analysis)

**Fixes applied**:
1. Enhanced table comments with `SECURITY NOTE` sections
2. Added indexes:
   - `idx_task_registry_created_at`: for pagination by creation time
   - `idx_task_registry_active_created_at`: partial index for active task queries
   - `idx_task_events_error_code_ts`: for incident analysis by error code

*Files modified*: `001_task_persistence_up.sql`, `001_task_persistence_down.sql`

### FIX-11. Operational recommendations: connection pooling and session management

**Issues found**:
In high-concurrency scenarios, long-lived or improperly closed connections may exhaust the connection pool.

**Recommendations** (application layer):
1. **Connection pool sizing**: Use `(cores * 2) + effective_spindle_count` formula

---

## 12. Day-4.2 execution addendum (2026-04-04)

Execution outcomes aligned to this review pack:

1. Runtime persistence switch is active (`sqlite/postgres`), with default kept at `sqlite` for compatibility.
2. CI now enforces:
   - PostgreSQL smoke gate (`tests/test_tasks_submit.py` with postgres persistence + memory queue)
   - RabbitMQ + PostgreSQL integration gate (`tests/test_tasks_rabbitmq_e2e.py`)
3. VM regression matrix passed:
   - postgres + memory: `27 passed`
   - postgres + rabbitmq: `1 passed`
4. Hidden persistence defects found during integration were fixed and re-verified:
   - state/event persistence order for FK safety
   - explicit `created_at` in postgres upsert path
   - governance-aware clear behavior under append-only policy
2. **Timeouts**: `connect_timeout=10s`, `socket_timeout=30s`, `statement_timeout=30s`
3. **Idle cleanup**: Set `idle_in_transaction_session_timeout = 5min`
4. **Periodic maintenance**: Clean up idle sessions older than 1 hour

*Files modified*: `EXPERT_DESIGN_REVIEW.md`, `DB_SCHEMA_OPTIMIZATION.md`

### FIX-12. Extensibility: event table partitioning strategy

**Issues found**:
While the composite PK structure supports partitioning, specific partitioning guidance was missing.

**Recommendations**:
1. **Partition key**: Range partition on `ts` column
2. **Granularity**: Monthly partitions for 100M+ events/year scenarios
3. **Maintenance**: Archive cold data to historical tables or object storage

The composite PK `(task_id, ts, event_id)` enables partition pruning for task-scoped queries.

*Files modified*: `001_task_persistence_up.sql` (table comments), `EXPERT_DESIGN_REVIEW.md`

---

## 12. Known limitations in this stage

1. no partitioning strategy yet for very high event volume. **(Addressed in FIX-12: documented recommended approach)**
2. no archival table for cold history yet.
3. no runtime code switch included in this review pack.
4. atomic transition function is available, but schema does not force all writers to use it.
5. sensitive-field encryption is not enforced by schema and should be handled by application policy. **(Addressed in FIX-10: enhanced security documentation)**
6. reactivation of soft-deleted tasks is policy-driven and requires clearing deleted_at before lifecycle writes.

Design boundary note:

1. DB function is available, but strict atomicity still depends on runtime adopting this function as the primary write path.

These are deliberate stage boundaries, not omissions.
