# 接口契约（Practice / Files / Tasks / Agents / Analytics）

## 5.4 Practice（答辩演练）

| 方法与路径 | 请求 | 成功 data | 关键错误码 |
|---|---|---|---|
| POST /api/v1/practice/questions | project_id, question_count, difficulty | questions[] | PRACTICE_CONTEXT_MISSING |
| POST /api/v1/practice/evaluate | session_id, question_id, answer | score, dimensions, feedback | PRACTICE_EVAL_FAILED |

---

## 5.5 Files（文件管家）

| 方法与路径 | 请求 | 成功 data | 关键错误码 |
|---|---|---|---|
| POST /api/v1/files/scan | root_path, filters, exclude_patterns | scan_summary, file_count | FILE_PATH_NOT_ALLOWED |
| POST /api/v1/files/organize | scan_id, strategy, dry_run | plan_id, actions[] | FILE_PLAN_INVALID |
| POST /api/v1/files/execute | plan_id, confirm_token, dry_run=false | execution_id, progress_url | FILE_EXECUTION_CONFLICT |
| POST /api/v1/files/rollback | execution_id, reason | rollback_id, restored_count | FILE_ROLLBACK_NOT_FOUND, FILE_ROLLBACK_FAILED |

---

## 5.6 Tasks（多AI协同）

| 方法与路径 | 请求 | 成功 data | 关键错误码 |
|---|---|---|---|
| POST /api/v1/tasks/submit | task_type, priority, required_capabilities, payload | task_id, queue, sla_ms | TASK_QUEUE_TIMEOUT |
| GET /api/v1/tasks/{task_id} | path参数 task_id | task_status | TASK_NOT_FOUND |
| POST /api/v1/tasks/{task_id}/cancel | reason | canceled=true | TASK_ALREADY_FINISHED, TASK_CANCEL_REJECTED |

---

## 5.7 Agents / Analytics

| 方法与路径 | 请求 | 成功 data | 关键错误码 |
|---|---|---|---|
| GET /api/v1/agents/capabilities | 无 | agents[] | RESOURCE_NOT_FOUND |
| GET /api/v1/analytics/report | from, to, scope | report_summary | INVALID_ARGUMENT |