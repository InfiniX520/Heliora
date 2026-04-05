BEGIN;

-- FIX-08：为 up 脚本中创建的所有索引添加显式 DROP INDEX 语句
-- 之前 down 脚本依赖 DROP TABLE 隐式级联删除索引
-- 显式删除使回滚意图清晰，并在表可能保留的环境中安全
-- （例如部分回滚或仅索引清理场景）

-- FIX-08：在删除表之前显式删除索引以使意图清晰
-- FIX-10：为新索引（error_code、created_at 变体）添加删除
DROP INDEX IF EXISTS idx_task_events_error_code_ts;
DROP INDEX IF EXISTS idx_task_events_operator_ts;
DROP INDEX IF EXISTS idx_task_events_trace_id_ts;
DROP INDEX IF EXISTS idx_task_events_event_type_ts;
DROP INDEX IF EXISTS uidx_task_events_event_id;

DROP INDEX IF EXISTS idx_task_registry_active_created_at;
DROP INDEX IF EXISTS idx_task_registry_created_at;
DROP INDEX IF EXISTS idx_task_registry_deleted_at;
DROP INDEX IF EXISTS idx_task_registry_active_status_updated_at;
DROP INDEX IF EXISTS idx_task_registry_status_updated_at;
DROP INDEX IF EXISTS idx_task_registry_updated_at;

-- 先删除子表以满足外键约束
DROP TABLE IF EXISTS task_events;
DROP TABLE IF EXISTS task_registry;

-- 删除函数。触发器函数在表之后删除（触发器已随表一起消失）
-- FIX-08：更新 app_task_transition_with_event 的函数签名以包含
-- FIX-05 中添加的新的 p_expected_version INTEGER 参数
DROP FUNCTION IF EXISTS app_task_events_block_truncate();
DROP FUNCTION IF EXISTS app_task_events_enforce_immutable();
DROP FUNCTION IF EXISTS app_task_transition_with_event(
    VARCHAR,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    TEXT,
    JSONB,
    VARCHAR,
    VARCHAR,
    VARCHAR,
    INTEGER
);
DROP FUNCTION IF EXISTS app_task_registry_prepare_row();
DROP FUNCTION IF EXISTS app_task_registry_validate_transition();

COMMIT;
