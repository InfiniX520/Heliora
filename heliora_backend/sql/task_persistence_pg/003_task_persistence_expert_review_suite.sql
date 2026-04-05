BEGIN;

-- Expert review suite for task persistence schema.
-- Goal: provide deterministic positive/negative checks without permanent data changes.
-- All test keys are deterministic; script ends with ROLLBACK so no cleanup is needed.

-- -----------------------------------------------------------------------------
-- Case A: happy path lifecycle + version monotonicity
-- -----------------------------------------------------------------------------
INSERT INTO task_registry (task_id, status, payload_json)
VALUES (
    'task_suite_001',
    'created',
    '{"task_type":"review","priority":"P2","queue":"normal.queue"}'::jsonb
);

DO $$
DECLARE
    v_before INTEGER;
    v_after  INTEGER;
BEGIN
    SELECT version INTO v_before FROM task_registry WHERE task_id = 'task_suite_001';

    UPDATE task_registry SET status = 'routed'    WHERE task_id = 'task_suite_001';
    UPDATE task_registry SET status = 'queued'    WHERE task_id = 'task_suite_001';
    UPDATE task_registry SET status = 'running'   WHERE task_id = 'task_suite_001';
    UPDATE task_registry SET status = 'completed' WHERE task_id = 'task_suite_001';

    SELECT version INTO v_after FROM task_registry WHERE task_id = 'task_suite_001';

    IF v_after <= v_before THEN
        RAISE EXCEPTION 'version monotonicity violated: before=% after=%', v_before, v_after;
    END IF;
END;
$$;

-- FIX-02 verification: when caller omits timestamps, DB defaults should be assigned.
DO $$
DECLARE
    v_created TIMESTAMPTZ;
    v_now     TIMESTAMPTZ := NOW();
BEGIN
    SELECT created_at INTO v_created
    FROM task_registry WHERE task_id = 'task_suite_001';

    -- created_at must be within 5 seconds of NOW() when insert omits timestamps.
    IF ABS(EXTRACT(EPOCH FROM (v_created - v_now))) > 5 THEN
        RAISE EXCEPTION 'created_at default assignment failed: got %', v_created;
    END IF;
END;
$$;

-- FIX-02 compatibility: explicit historical timestamps/version should be preserved.
INSERT INTO task_registry (
    task_id,
    status,
    payload_json,
    created_at,
    updated_at,
    version
) VALUES (
    'task_suite_006',
    'created',
    '{"task_type":"review_backfill"}'::jsonb,
    '2024-01-01 00:00:00+00'::timestamptz,
    '2024-01-02 00:00:00+00'::timestamptz,
    9
);

DO $$
DECLARE
    v_created_at TIMESTAMPTZ;
    v_updated_at TIMESTAMPTZ;
    v_version INTEGER;
BEGIN
    SELECT created_at, updated_at, version
    INTO v_created_at, v_updated_at, v_version
    FROM task_registry
    WHERE task_id = 'task_suite_006';

    IF v_created_at <> '2024-01-01 00:00:00+00'::timestamptz
       OR v_updated_at <> '2024-01-02 00:00:00+00'::timestamptz
       OR v_version <> 9 THEN
        RAISE EXCEPTION 'expected historical backfill values to be preserved, got created_at=%, updated_at=%, version=%',
            v_created_at, v_updated_at, v_version;
    END IF;
END;
$$;

-- -----------------------------------------------------------------------------
-- Case B: invalid transition must fail
-- completed -> running should be rejected
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    BEGIN
        UPDATE task_registry SET status = 'running' WHERE task_id = 'task_suite_001';
        RAISE EXCEPTION 'expected invalid transition to fail, but update succeeded';
    EXCEPTION
        WHEN check_violation THEN
            NULL;
    END;
END;
$$;

-- -----------------------------------------------------------------------------
-- Case I: atomic transition function should update registry + insert event
-- -----------------------------------------------------------------------------
INSERT INTO task_registry (task_id, status, payload_json)
VALUES ('task_suite_004', 'queued', '{"task_type":"review_atomic"}'::jsonb);

SELECT app_task_transition_with_event(
    'task_suite_004',
    'running',
    'evt_suite_fn_001',
    'running',
    'transition by atomic function',
    '{"source":"app_task_transition_with_event"}'::jsonb,
    'system',
    NULL,
    'trc_suite_fn_001'
    -- p_expected_version NULL: optimistic lock check skipped
);

DO $$
DECLARE
    v_status      VARCHAR(16);
    v_event_count INTEGER;
BEGIN
    SELECT status INTO v_status
    FROM task_registry WHERE task_id = 'task_suite_004';

    IF v_status <> 'running' THEN
        RAISE EXCEPTION 'expected task_suite_004 status running, got %', v_status;
    END IF;

    SELECT COUNT(*) INTO v_event_count
    FROM task_events
    WHERE event_id    = 'evt_suite_fn_001'
      AND task_id     = 'task_suite_004'
      AND from_status = 'queued'
      AND to_status   = 'running';

    IF v_event_count <> 1 THEN
        RAISE EXCEPTION 'expected one matched event for atomic transition, got %', v_event_count;
    END IF;
END;
$$;

-- -----------------------------------------------------------------------------
-- Case I2: optimistic lock conflict must raise serialization_failure (FIX-05)
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    v_version INTEGER;
BEGIN
    SELECT version INTO v_version FROM task_registry WHERE task_id = 'task_suite_004';

    BEGIN
        -- Pass stale version (current - 1) to trigger conflict.
        PERFORM app_task_transition_with_event(
            'task_suite_004',
            'completed',
            'evt_suite_fn_002',
            'completed',
            'optimistic lock conflict test',
            '{}'::jsonb,
            'system',
            NULL,
            NULL,
            v_version - 1  -- intentionally stale
        );
        RAISE EXCEPTION 'expected serialization_failure, but call succeeded';
    EXCEPTION
        WHEN serialization_failure THEN
            NULL;
    END;
END;
$$;

-- Case I3: correct version should succeed
DO $$
DECLARE
    v_version INTEGER;
BEGIN
    SELECT version INTO v_version FROM task_registry WHERE task_id = 'task_suite_004';

    PERFORM app_task_transition_with_event(
        'task_suite_004',
        'completed',
        'evt_suite_fn_003',
        'completed',
        'optimistic lock success test',
        '{}'::jsonb,
        'system',
        NULL,
        NULL,
        v_version  -- correct version
    );
END;
$$;

-- -----------------------------------------------------------------------------
-- Case J: TRUNCATE on task_events must fail
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    BEGIN
        EXECUTE 'TRUNCATE TABLE task_events';
        RAISE EXCEPTION 'expected TRUNCATE prohibition, but TRUNCATE succeeded';
    EXCEPTION
        WHEN check_violation THEN
            NULL;
    END;
END;
$$;

-- -----------------------------------------------------------------------------
-- Case B2: running -> retrying -> running should pass
-- -----------------------------------------------------------------------------
INSERT INTO task_registry (task_id, status, payload_json)
VALUES ('task_suite_003', 'queued', '{"task_type":"review_retry"}'::jsonb);

DO $$
DECLARE
    v_status VARCHAR(16);
BEGIN
    UPDATE task_registry SET status = 'running'  WHERE task_id = 'task_suite_003';
    UPDATE task_registry SET status = 'retrying' WHERE task_id = 'task_suite_003';
    UPDATE task_registry SET status = 'running'  WHERE task_id = 'task_suite_003';

    SELECT status INTO v_status FROM task_registry WHERE task_id = 'task_suite_003';
    IF v_status <> 'running' THEN
        RAISE EXCEPTION 'expected status running, got %', v_status;
    END IF;
END;
$$;

-- -----------------------------------------------------------------------------
-- Case B3: failed is terminal (failed -> retrying must fail)
-- -----------------------------------------------------------------------------
UPDATE task_registry SET status = 'failed' WHERE task_id = 'task_suite_003';

DO $$
BEGIN
    BEGIN
        UPDATE task_registry SET status = 'retrying' WHERE task_id = 'task_suite_003';
        RAISE EXCEPTION 'expected failed -> retrying to fail, but update succeeded';
    EXCEPTION
        WHEN check_violation THEN
            NULL;
    END;
END;
$$;

-- -----------------------------------------------------------------------------
-- Case C: metadata_json must be object
-- -----------------------------------------------------------------------------
INSERT INTO task_registry (task_id, status, payload_json)
VALUES ('task_suite_002', 'queued', '{}'::jsonb);

DO $$
BEGIN
    BEGIN
        INSERT INTO task_events (
            event_id, task_id, event_type, from_status, to_status, message, metadata_json
        ) VALUES (
            'evt_suite_bad_meta',
            'task_suite_002',
            'queued',
            'routed',
            'queued',
            'bad metadata test',
            '[]'::jsonb  -- array, not object
        );
        RAISE EXCEPTION 'expected metadata object constraint to fail, but insert succeeded';
    EXCEPTION
        WHEN check_violation THEN
            NULL;
    END;
END;
$$;

-- -----------------------------------------------------------------------------
-- Case D: duplicate event_id must fail
-- -----------------------------------------------------------------------------
INSERT INTO task_events (
    event_id, task_id, event_type, from_status, to_status, message, metadata_json, operator, trace_id
) VALUES (
    'evt_suite_dup_001',
    'task_suite_002',
    'queued',
    'routed',
    'queued',
    'first duplicate key row',
    '{}'::jsonb,
    'system',
    'trc_suite_001'
);

DO $$
BEGIN
    BEGIN
        INSERT INTO task_events (
            event_id, task_id, event_type, from_status, to_status, message, metadata_json
        ) VALUES (
            'evt_suite_dup_001',
            'task_suite_002',
            'running',
            'queued',
            'running',
            'second duplicate key row',
            '{}'::jsonb
        );
        RAISE EXCEPTION 'expected unique violation on event_id, but insert succeeded';
    EXCEPTION
        WHEN unique_violation THEN
            NULL;
    END;
END;
$$;

-- -----------------------------------------------------------------------------
-- Case L: invalid event_type must fail (FIX-04)
-- Previously event_type was unconstrained; now must match status vocabulary + 'info'.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    BEGIN
        INSERT INTO task_events (
            event_id, task_id, event_type, from_status, to_status, message, metadata_json
        ) VALUES (
            'evt_suite_bad_type',
            'task_suite_002',
            'INVALID_TYPE',  -- not in vocab
            'queued',
            'running',
            'bad event type test',
            '{}'::jsonb
        );
        RAISE EXCEPTION 'expected event_type vocab constraint to fail, but insert succeeded';
    EXCEPTION
        WHEN check_violation THEN
            NULL;
    END;
END;
$$;

-- Case L2: 'info' event_type should be accepted (non-transition diagnostic event).
INSERT INTO task_events (
    event_id, task_id, event_type, from_status, to_status, message, metadata_json
) VALUES (
    'evt_suite_info_001',
    'task_suite_002',
    'info',   -- generic diagnostic label
    NULL,
    'queued',
    'diagnostic note attached to task',
    '{"note":"health check passed"}'::jsonb
);

-- -----------------------------------------------------------------------------
-- Case E: explain plans for core read patterns
-- -----------------------------------------------------------------------------
EXPLAIN (COSTS OFF)
SELECT task_id, status, updated_at
FROM task_registry
WHERE deleted_at IS NULL AND status = 'queued'
ORDER BY updated_at DESC
LIMIT 20;

EXPLAIN (COSTS OFF)
SELECT task_id, status, updated_at
FROM task_registry
WHERE status = 'queued'
ORDER BY updated_at DESC
LIMIT 20;

EXPLAIN (COSTS OFF)
SELECT event_id, event_type, ts
FROM task_events
WHERE task_id = 'task_suite_001'
ORDER BY ts ASC
LIMIT 200;

EXPLAIN (COSTS OFF)
SELECT event_id, task_id, ts
FROM task_events
WHERE trace_id = 'trc_suite_001'
ORDER BY ts DESC
LIMIT 100;

-- FIX-07 verification: operator index should be used for operator-scoped queries.
EXPLAIN (COSTS OFF)
SELECT event_id, task_id, ts
FROM task_events
WHERE operator = 'worker_daemon'
ORDER BY ts DESC
LIMIT 50;

-- FIX-10 verification: error_code index should be used for error analysis queries.
EXPLAIN (COSTS OFF)
SELECT event_id, task_id, error_code, ts
FROM task_events
WHERE error_code = 'E_SIM_FAIL'
ORDER BY ts DESC
LIMIT 50;

-- FIX-10 verification: created_at index should be used for recent tasks queries.
EXPLAIN (COSTS OFF)
SELECT task_id, status, created_at
FROM task_registry
WHERE deleted_at IS NULL
ORDER BY created_at DESC
LIMIT 20;

-- -----------------------------------------------------------------------------
-- Case F: task_events must be append-only (UPDATE should fail)
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    BEGIN
        UPDATE task_events
        SET message = 'tampered'
        WHERE event_id = 'evt_suite_dup_001';
        RAISE EXCEPTION 'expected append-only protection to reject UPDATE, but update succeeded';
    EXCEPTION
        WHEN check_violation THEN
            NULL;
    END;
END;
$$;

-- -----------------------------------------------------------------------------
-- Case H: soft delete marker should be writable and query-visible
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    v_deleted_at TIMESTAMPTZ;
BEGIN
    UPDATE task_registry
    SET deleted_at = NOW()
    WHERE task_id = 'task_suite_003';

    SELECT deleted_at INTO v_deleted_at
    FROM task_registry WHERE task_id = 'task_suite_003';

    IF v_deleted_at IS NULL THEN
        RAISE EXCEPTION 'expected deleted_at to be set for task_suite_003';
    END IF;
END;
$$;

-- -----------------------------------------------------------------------------
-- Case K: soft-deleted task must reject status transition
-- -----------------------------------------------------------------------------
INSERT INTO task_registry (task_id, status, payload_json)
VALUES ('task_suite_005', 'queued', '{}'::jsonb);

UPDATE task_registry SET deleted_at = NOW() WHERE task_id = 'task_suite_005';

DO $$
BEGIN
    BEGIN
        UPDATE task_registry SET status = 'running' WHERE task_id = 'task_suite_005';
        RAISE EXCEPTION 'expected status transition on soft-deleted task to fail, but update succeeded';
    EXCEPTION
        WHEN check_violation THEN
            NULL;
    END;
END;
$$;

-- -----------------------------------------------------------------------------
-- Case G: payload_json must be JSON object (array should fail)
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    BEGIN
        INSERT INTO task_registry (task_id, status, payload_json)
        VALUES ('task_suite_bad_payload', 'created', '[]'::jsonb);
        RAISE EXCEPTION 'expected payload_json object constraint to fail, but insert succeeded';
    EXCEPTION
        WHEN check_violation THEN
            NULL;
    END;
END;
$$;

-- -----------------------------------------------------------------------------
-- Human-readable verification output
-- -----------------------------------------------------------------------------
SELECT task_id, status, version, created_at, updated_at, deleted_at
FROM task_registry
WHERE task_id IN ('task_suite_001', 'task_suite_002', 'task_suite_003', 'task_suite_004', 'task_suite_005', 'task_suite_006')
ORDER BY task_id;

SELECT task_id, event_id, event_type, from_status, to_status, operator, error_code, trace_id, ts
FROM task_events
WHERE task_id IN ('task_suite_001', 'task_suite_002', 'task_suite_004')
ORDER BY ts ASC, event_id ASC;

ROLLBACK;
