# Cutover Observation Window Report (VM)

- generated_at_local: 2026-04-05 13:11:01
- scope: second release window observation (Day-4.5)
- related_preflight: heliora_backend/.release-reports/release_preflight_20260405_131017.md

## Runtime Health

- health: {"code":"OK","message":"success","data":{"status":"healthy"}}
- worker_pid: 8968
- worker_state: running

## Error Signature Scan

- api_error_hits: 0
- worker_error_hits: 0
- scan_pattern: task state/event persistence failed|traceback|[error]|connection timeout|psycopg.errors

## Log Window Metadata

- api_lines: 4056
- worker_lines: 7945
- worker_window_start: 2026-04-05 04:00:00,548
- worker_window_end: 2026-04-05 05:11:04,193
- api_mtime_utc: 2026-04-05 05:11:13.958321764 +0000
- worker_mtime_utc: 2026-04-05 05:11:13.958321764 +0000
- api_size_bytes: 318628
- worker_size_bytes: 788367

## Tail Snapshot (latest)

- api_tail: continuous 200 OK on /api/v1/tasks/consume-next and 200 OK on /health
- worker_tail: continuous consume-next 200 OK with no queued task, no exception pattern observed

## Conclusion

- observation_result: PASS
- release_window_status: stable
- decision: conditions satisfied for ANN audit promotion to blocking gate
