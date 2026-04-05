# Cutover Observation Window Report (VM)

- generated_at_local: 2026-04-05 12:46:17
- target_vm: Heliora-VM
- remote_backend_dir: /home/heliora/heliora_backend
- scope: post-cutover observation and final Go sign-off readiness

## 1. Runtime Health Snapshot

1. snapshot_utc: 2026-04-05T04:45:52Z
2. health response:
   - {"code":"OK","message":"success","data":{"status":"healthy"},"trace_id":"49e17cae61864198","ts":"2026-04-05T04:45:52.785007+00:00"}
3. worker state:
   - worker_state=running
   - worker_pid=8968

## 2. Error Signature Scan

Scan patterns:
- task state/event persistence failed
- traceback
- [error]
- connection timeout
- psycopg.errors

Results:
1. api_error_hits=0
2. worker_error_hits=0

## 3. Observation Duration Evidence

1. worker_window_start=2026-04-05 04:00:00
2. worker_window_end=2026-04-05 04:45:52
3. observed_duration=45m52s (>= 15 minutes requirement met)

Auxiliary log metadata:
1. api_mtime=2026-04-05 04:45:59.742398553 +0000
2. worker_mtime=2026-04-05 04:45:59.743398561 +0000
3. api_lines=2650
4. worker_lines=5135

## 4. Tail Evidence

API tail (latest 8 lines): all `200 OK` for health/consume-next.

Worker tail (latest 8 lines): repeated `consume-next` HTTP 200 and `no queued task` info logs, no error signatures.

## 5. Observation Decision

- rollback_triggered: no
- decision: observation window PASSED
- signoff_recommendation: keep postgres runtime and proceed to final release sign-off record
