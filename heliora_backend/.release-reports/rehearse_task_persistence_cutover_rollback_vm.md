Administrator@DESKTOP-RD7D8L3 MINGW64 /e/Zero9/Heliora/heliora_backend
$ bash scripts/rehearse_task_persistence_cutover_rollback_vm.sh
[rehearsal] start postgres cutover matrix
[matrix] run env consistency preflight
[+] Environment consistency check passed: /home/heliora/heliora_backend/.env
[matrix] ssh ok: Heliora-VM
[matrix] backend path: /home/heliora/heliora_backend
[matrix] postgres container: heliora-postgres
[profile:postgres-memory] start
BEGIN
CREATE TABLE
CREATE FUNCTION
CREATE FUNCTION
DROP TRIGGER
NOTICE:  trigger "trg_task_registry_10_validate_transition" for relation "task_registry" does not exist, skipping
CREATE TRIGGER
DROP TRIGGER
NOTICE:  trigger "trg_task_registry_20_prepare_row" for relation "task_registry" does not exist, skipping
CREATE TRIGGER
CREATE TABLE
CREATE INDEX
CREATE FUNCTION
CREATE FUNCTION
DROP TRIGGER
NOTICE:  trigger "trg_task_events_10_enforce_immutable" for relation "task_events" does not exist, skipping
CREATE TRIGGER
CREATE FUNCTION
COMMENT
DROP TRIGGER
NOTICE:  trigger "trg_task_events_20_block_truncate" for relation "task_events" does not exist, skipping
CREATE TRIGGER
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
DROP INDEX
NOTICE:  index "idx_task_events_trace_id" does not exist, skipping
CREATE INDEX
CREATE INDEX
CREATE INDEX
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMIT
...........................                                              [100%]
==================================== PASSES ====================================
___________ test_submit_task_fallbacks_on_recoverable_rabbitmq_error ___________
------------------------------ Captured log call -------------------------------
WARNING  app.services.task_queue:task_queue.py:374 Queue op publish failed on rabbitmq backend, fallback to memory backend: rabbitmq connection lost
___________________ test_registry_rejects_invalid_transition ___________________
------------------------------ Captured log call -------------------------------
WARNING  app.services.task_registry:task_registry.py:246 reject invalid transition: task_id=task_ffd67b6981 from=queued to=completed
=========================== short test summary info ============================
PASSED tests/test_tasks_submit.py::test_submit_task_requires_idempotency_key
PASSED tests/test_tasks_submit.py::test_submit_task_returns_accepted
PASSED tests/test_tasks_submit.py::test_submit_task_replay_returns_same_task
PASSED tests/test_tasks_submit.py::test_submit_task_reuse_key_with_different_payload_returns_conflict
PASSED tests/test_tasks_submit.py::test_get_task_status_after_submit
PASSED tests/test_tasks_submit.py::test_get_task_status_not_found
PASSED tests/test_tasks_submit.py::test_get_task_events_after_submit
PASSED tests/test_tasks_submit.py::test_get_task_events_supports_pagination
PASSED tests/test_tasks_submit.py::test_get_task_events_supports_event_type_filter
PASSED tests/test_tasks_submit.py::test_get_task_events_rejects_invalid_start_ts
PASSED tests/test_tasks_submit.py::test_get_task_events_rejects_reversed_time_window
PASSED tests/test_tasks_submit.py::test_consume_next_task_completes_and_updates_status
PASSED tests/test_tasks_submit.py::test_consume_next_task_force_fail_enters_retrying
PASSED tests/test_tasks_submit.py::test_consume_force_fail_requeues_before_max_attempts
PASSED tests/test_tasks_submit.py::test_consume_force_fail_dead_letters_on_max_attempts
PASSED tests/test_tasks_submit.py::test_submit_task_fallbacks_on_recoverable_rabbitmq_error
PASSED tests/test_tasks_submit.py::test_submit_task_does_not_fallback_on_non_recoverable_rabbitmq_error
PASSED tests/test_tasks_submit.py::test_task_events_are_persisted
PASSED tests/test_tasks_submit.py::test_consume_next_task_noop_when_empty_queue
PASSED tests/test_tasks_submit.py::test_get_task_events_not_found
PASSED tests/test_tasks_submit.py::test_submit_memory_task_routes_to_memory_queue
PASSED tests/test_tasks_submit.py::test_cancel_task_sets_status_to_canceled
PASSED tests/test_tasks_submit.py::test_cancel_task_rejects_finished_task
PASSED tests/test_tasks_submit.py::test_consume_skips_canceled_task
PASSED tests/test_tasks_submit.py::test_registry_rejects_invalid_transition
PASSED tests/test_tasks_submit.py::test_get_task_events_reads_persistent_store_when_task_missing
PASSED tests/test_tasks_submit.py::test_get_task_status_reads_persistent_registry_when_memory_missing
BEGIN
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP TABLE
DROP TABLE
DROP FUNCTION
DROP FUNCTION
DROP FUNCTION
DROP FUNCTION
DROP FUNCTION
COMMIT
[profile:postgres-memory] passed
[profile:postgres-rabbitmq] start
BEGIN
CREATE TABLE
CREATE FUNCTION
CREATE FUNCTION
DROP TRIGGER
NOTICE:  trigger "trg_task_registry_10_validate_transition" for relation "task_registry" does not exist, skipping
CREATE TRIGGER
DROP TRIGGER
NOTICE:  trigger "trg_task_registry_20_prepare_row" for relation "task_registry" does not exist, skipping
CREATE TRIGGER
CREATE TABLE
CREATE INDEX
CREATE FUNCTION
CREATE FUNCTION
NOTICE:  trigger "trg_task_events_10_enforce_immutable" for relation "task_events" does not exist, skipping
DROP TRIGGER
CREATE TRIGGER
CREATE FUNCTION
COMMENT
NOTICE:  trigger "trg_task_events_20_block_truncate" for relation "task_events" does not exist, skipping
DROP TRIGGER
CREATE TRIGGER
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
NOTICE:  index "idx_task_events_trace_id" does not exist, skipping
DROP INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
COMMIT
.                                                                        [100%]
==================================== PASSES ====================================
=========================== short test summary info ============================
PASSED tests/test_tasks_rabbitmq_e2e.py::test_rabbitmq_retry_and_dead_letter_e2e
BEGIN
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP INDEX
DROP TABLE
DROP TABLE
DROP FUNCTION
DROP FUNCTION
DROP FUNCTION
DROP FUNCTION
DROP FUNCTION
COMMIT
[profile:postgres-rabbitmq] passed
[matrix] all profiles passed
[rehearsal] start sqlite rollback validation
...........................                                              [100%]
==================================== PASSES ====================================
___________ test_submit_task_fallbacks_on_recoverable_rabbitmq_error ___________
------------------------------ Captured log call -------------------------------
WARNING  app.services.task_queue:task_queue.py:374 Queue op publish failed on rabbitmq backend, fallback to memory backend: rabbitmq connection lost
___________________ test_registry_rejects_invalid_transition ___________________
------------------------------ Captured log call -------------------------------
WARNING  app.services.task_registry:task_registry.py:246 reject invalid transition: task_id=task_6f5a1c2c9f from=queued to=completed
=========================== short test summary info ============================
PASSED tests/test_tasks_submit.py::test_submit_task_requires_idempotency_key
PASSED tests/test_tasks_submit.py::test_submit_task_returns_accepted
PASSED tests/test_tasks_submit.py::test_submit_task_replay_returns_same_task
PASSED tests/test_tasks_submit.py::test_submit_task_reuse_key_with_different_payload_returns_conflict
PASSED tests/test_tasks_submit.py::test_get_task_status_after_submit
PASSED tests/test_tasks_submit.py::test_get_task_status_not_found
PASSED tests/test_tasks_submit.py::test_get_task_events_after_submit
PASSED tests/test_tasks_submit.py::test_get_task_events_supports_pagination
PASSED tests/test_tasks_submit.py::test_get_task_events_supports_event_type_filter
PASSED tests/test_tasks_submit.py::test_get_task_events_rejects_invalid_start_ts
PASSED tests/test_tasks_submit.py::test_get_task_events_rejects_reversed_time_window
PASSED tests/test_tasks_submit.py::test_consume_next_task_completes_and_updates_status
PASSED tests/test_tasks_submit.py::test_consume_next_task_force_fail_enters_retrying
PASSED tests/test_tasks_submit.py::test_consume_force_fail_requeues_before_max_attempts
PASSED tests/test_tasks_submit.py::test_consume_force_fail_dead_letters_on_max_attempts
PASSED tests/test_tasks_submit.py::test_submit_task_fallbacks_on_recoverable_rabbitmq_error
PASSED tests/test_tasks_submit.py::test_submit_task_does_not_fallback_on_non_recoverable_rabbitmq_error
PASSED tests/test_tasks_submit.py::test_task_events_are_persisted
PASSED tests/test_tasks_submit.py::test_consume_next_task_noop_when_empty_queue
PASSED tests/test_tasks_submit.py::test_get_task_events_not_found
PASSED tests/test_tasks_submit.py::test_submit_memory_task_routes_to_memory_queue
PASSED tests/test_tasks_submit.py::test_cancel_task_sets_status_to_canceled
PASSED tests/test_tasks_submit.py::test_cancel_task_rejects_finished_task
PASSED tests/test_tasks_submit.py::test_consume_skips_canceled_task
PASSED tests/test_tasks_submit.py::test_registry_rejects_invalid_transition
PASSED tests/test_tasks_submit.py::test_get_task_events_reads_persistent_store_when_task_missing
PASSED tests/test_tasks_submit.py::test_get_task_status_reads_persistent_registry_when_memory_missing
[rehearsal] sqlite rollback validation passed
[rehearsal] cutover and rollback rehearsal passed

Administrator@DESKTOP-RD7D8L3 MINGW64 /e/Zero9/Heliora/heliora_backend
$
