# Release Window Preflight Report

- generated_at_utc: 2026-04-05T02:19:18Z
- backend_dir: /e/Zero9/Heliora/heliora_backend
- env_file: .env
- overall_status: PASS

## Step Results

| Step | Outcome | Duration |
| --- | --- | --- |
| env consistency | PASS | 0s |
| vm sql review | PASS | 3s |
| vm runtime matrix | PASS | 9s |
| vm cutover rollback rehearsal | PASS | 13s |


## Execution Flags

- run_sql_review: true
- run_matrix: true
- run_rehearsal: true

## Notes

- This report is generated on host side and can be attached to release Go/No-Go review.
- Use together with project release execution checklist evidence section.
