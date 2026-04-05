BEGIN;

-- 1) Seed one task row.
-- FIX-09: when created_at/updated_at/version are omitted, DB defaults are applied.
INSERT INTO task_registry (
    task_id,
    status,
    payload_json
) VALUES (
    'task_verify_001',
    'queued',
    '{"task_type":"verify","priority":"P2","queue":"normal.queue"}'::jsonb
);

-- 1b) Historical backfill values should be preserved when explicitly supplied.
INSERT INTO task_registry (
    task_id,
    status,
    payload_json,
    created_at,
    updated_at,
    version
) VALUES (
    'task_verify_003',
    'created',
    '{"task_type":"verify_backfill"}'::jsonb,
    '2024-01-01 00:00:00+00'::timestamptz,
    '2024-01-02 00:00:00+00'::timestamptz,
    7
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
    WHERE task_id = 'task_verify_003';

    IF v_created_at <> '2024-01-01 00:00:00+00'::timestamptz
       OR v_updated_at <> '2024-01-02 00:00:00+00'::timestamptz
       OR v_version <> 7 THEN
        RAISE EXCEPTION 'backfill values were not preserved: created_at=%, updated_at=%, version=%',
            v_created_at, v_updated_at, v_version;
    END IF;
END;
$$;

-- 2) Valid transitions should pass.
UPDATE task_registry SET status = 'running' WHERE task_id = 'task_verify_001';
UPDATE task_registry SET status = 'completed' WHERE task_id = 'task_verify_001';

-- 2b) Retry lifecycle should pass; failed must stay terminal.
INSERT INTO task_registry (
    task_id,
    status,
    payload_json
) VALUES (
    'task_verify_002',
    'queued',
    '{"task_type":"verify_retry","priority":"P2","queue":"normal.queue"}'::jsonb
);

SELECT app_task_transition_with_event(
    'task_verify_002',
    'running',
    'evt_verify_003',
    'running',
    'worker picked retry task',
    '{"queue":"normal.queue"}'::jsonb,
    'worker_daemon',
    NULL,
    'trc_verify_002'
    -- p_expected_version omitted: NULL skips optimistic lock check (backward-compatible)
);

SELECT app_task_transition_with_event(
    'task_verify_002',
    'retrying',
    'evt_verify_004',
    'retrying',
    'task execution scheduled for retry',
    '{"reason":"simulated_retry"}'::jsonb,
    'worker_daemon',
    NULL,
    'trc_verify_002'
);

SELECT app_task_transition_with_event(
    'task_verify_002',
    'running',
    'evt_verify_005',
    'running',
    'worker picked retry task',
    '{"attempt":2}'::jsonb,
    'system',
    NULL,
    'trc_verify_002'
);

SELECT app_task_transition_with_event(
    'task_verify_002',
    'failed',
    'evt_verify_006',
    'failed',
    'task execution failed terminally',
    '{"reason":"simulated_failure"}'::jsonb,
    'worker_daemon',
    'E_SIM_FAIL',
    'trc_verify_002'
);

DO $$
BEGIN
    BEGIN
        UPDATE task_registry SET status = 'retrying' WHERE task_id = 'task_verify_002';
        RAISE EXCEPTION 'expected failed -> retrying to fail, but update succeeded';
    EXCEPTION
        WHEN check_violation THEN
            NULL;
    END;
END;
$$;

-- 3) Insert event samples.
-- FIX-09: event_type values must now match chk_task_events_event_type_vocab constraint (FIX-04).
-- 'running' and 'completed' are valid vocab entries, so these inserts are already compliant.
-- The insert order here is for direct-insert path testing only; prefer
-- app_task_transition_with_event for production writes to guarantee from_status accuracy.
INSERT INTO task_events (
    event_id,
    task_id,
    event_type,
    from_status,
    to_status,
    message,
    metadata_json,
    operator,
    trace_id
) VALUES
(
    'evt_verify_001',
    'task_verify_001',
    'running',
    'queued',
    'running',
    'worker picked task',
    '{"queue":"normal.queue"}'::jsonb,
    'worker_daemon',
    'trc_verify_001'
),
(
    'evt_verify_002',
    'task_verify_001',
    'completed',
    'running',
    'completed',
    'task execution completed',
    '{"summary":"ok"}'::jsonb,
    'worker_daemon',
    'trc_verify_001'
);

-- 4) Read checks.
SELECT task_id, status, version, created_at, updated_at, deleted_at
FROM task_registry
WHERE task_id IN ('task_verify_001', 'task_verify_002', 'task_verify_003')
ORDER BY task_id;

SELECT event_id, event_type, from_status, to_status, ts
FROM task_events
WHERE task_id IN ('task_verify_001', 'task_verify_002')
ORDER BY ts ASC, event_id ASC;

-- 5) Negative check (uncomment to validate rejection).
-- UPDATE task_registry SET status = 'created' WHERE task_id = 'task_verify_001';
-- TRUNCATE task_events;

ROLLBACK;
