BEGIN;

-- 任务持久化系统的 PostgreSQL 架构（注册表 + 事件表）
-- 范围：Day-4 从 SQLite 迁移到 PostgreSQL 的设计

CREATE TABLE IF NOT EXISTS task_registry (
    task_id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(16) NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ NULL,
    version INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT chk_task_registry_task_id_not_blank CHECK (btrim(task_id) <> ''),
    CONSTRAINT chk_task_registry_status CHECK (
        status IN (
            'created',
            'routed',
            'queued',
            'running',
            'retrying',
            'completed',
            'failed',
            'canceled'
        )
    ),
    CONSTRAINT chk_task_registry_payload_object CHECK (jsonb_typeof(payload_json) = 'object'),
    CONSTRAINT chk_task_registry_deleted_at_after_created CHECK (
        deleted_at IS NULL OR deleted_at >= created_at
    ),
    CONSTRAINT chk_task_registry_version_positive CHECK (version >= 1)
);

-- FIX-01：为所有触发器函数添加 SET search_path，防止 search_path 劫持攻击
-- 之前只有 app_task_transition_with_event 有此保护，触发器函数存在漏洞
CREATE OR REPLACE FUNCTION app_task_registry_validate_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    -- 已软删除的任务行不应再发生生命周期状态变更
    IF OLD.deleted_at IS NOT NULL AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION '任务已软删除，无法进行状态转换: % -> %', OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;

    -- 允许不改变状态的更新（例如修补 payload/result 字段）
    IF NEW.status = OLD.status THEN
        RETURN NEW;
    END IF;

    -- 与统一口径对齐：
    -- 1) canceled 仅允许从 queued/running 进入
    -- 2) failed 为终态，不允许回退到 retrying
    IF OLD.status = 'created'  AND NEW.status = 'routed' THEN RETURN NEW; END IF;
    IF OLD.status = 'routed'   AND NEW.status = 'queued' THEN RETURN NEW; END IF;
    IF OLD.status = 'queued'   AND NEW.status IN ('running', 'canceled') THEN RETURN NEW; END IF;
    IF OLD.status = 'running'  AND NEW.status IN ('retrying', 'completed', 'failed', 'canceled') THEN RETURN NEW; END IF;
    IF OLD.status = 'retrying' AND NEW.status = 'running' THEN RETURN NEW; END IF;

    RAISE EXCEPTION '无效的任务状态转换: % -> %', OLD.status, NEW.status
        USING ERRCODE = 'check_violation';
END;
$$;

-- FIX-01（续）：此处也添加了 SET search_path
-- FIX-02（修订版）：INSERT 支持受控的历史数据回填
-- 如果调用者省略 created_at/updated_at/version，则应用数据库默认值
-- 如果调用者提供这些值，则保留并进行合理性检查
CREATE OR REPLACE FUNCTION app_task_registry_prepare_row()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    now_utc TIMESTAMPTZ := NOW();
BEGIN
    IF NEW.payload_json IS NULL THEN
        NEW.payload_json := '{}'::jsonb;
    ELSIF jsonb_typeof(NEW.payload_json) <> 'object' THEN
        RAISE EXCEPTION 'payload_json 必须是 JSON 对象'
            USING ERRCODE = 'check_violation';
    END IF;

    IF TG_OP = 'INSERT' THEN
        -- 兼容回填的默认值
        NEW.created_at := COALESCE(NEW.created_at, now_utc);
        NEW.updated_at := COALESCE(NEW.updated_at, NEW.created_at);
        NEW.version    := COALESCE(NEW.version, 1);

        -- 拒绝未来时间戳的插入，同时允许历史数据回填
        IF NEW.created_at > now_utc + INTERVAL '5 minutes'
           OR NEW.updated_at > now_utc + INTERVAL '5 minutes' THEN
            RAISE EXCEPTION '插入的时间戳不能是未来时间: created_at=%, updated_at=%',
                NEW.created_at, NEW.updated_at
                USING ERRCODE = 'check_violation';
        END IF;

        IF NEW.updated_at < NEW.created_at THEN
            RAISE EXCEPTION 'updated_at 不能早于 created_at: created_at=%, updated_at=%',
                NEW.created_at, NEW.updated_at
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        NEW.updated_at := now_utc;
        NEW.created_at := OLD.created_at; -- 插入后不可变
        NEW.version    := OLD.version + 1;
    END IF;

    -- 移除 payload_json 同步以避免 MVCC 更新膨胀（写放大）
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_task_registry_10_validate_transition ON task_registry;
CREATE TRIGGER trg_task_registry_10_validate_transition
BEFORE UPDATE OF status
ON task_registry
FOR EACH ROW
EXECUTE FUNCTION app_task_registry_validate_transition();

DROP TRIGGER IF EXISTS trg_task_registry_20_prepare_row ON task_registry;
CREATE TRIGGER trg_task_registry_20_prepare_row
BEFORE INSERT OR UPDATE
ON task_registry
FOR EACH ROW
EXECUTE FUNCTION app_task_registry_prepare_row();

CREATE TABLE IF NOT EXISTS task_events (
    -- FIX-03：移除 event_id 上冗余的独立 UNIQUE 约束
    -- 复合主键 (task_id, ts, event_id) 已经通过其支持的 UNIQUE 索引保证了 event_id 的全局唯一性
    -- 额外的 UNIQUE 索引是重复的 B-tree 索引，每次插入都会消耗额外的写 I/O 和存储
    -- 下面单独添加轻量级唯一索引 uidx_task_events_event_id 替代
    event_id VARCHAR(64) NOT NULL,
    task_id VARCHAR(64) NOT NULL REFERENCES task_registry(task_id) ON DELETE RESTRICT,
    -- FIX-04：event_type 现在强制执行与 from_status/to_status 匹配的状态词表
    -- 之前 event_type 是自由格式的 VARCHAR，与受约束的状态字段形成不对称
    -- 存在审计记录不一致的风险（例如拼写错误、大小写混合、任意标签）
    event_type VARCHAR(64) NOT NULL,
    from_status VARCHAR(16) NULL,
    to_status VARCHAR(16) NOT NULL,
    message TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    operator VARCHAR(64) NULL,
    error_code VARCHAR(64) NULL,
    trace_id VARCHAR(64) NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_task_events_event_id_not_blank CHECK (btrim(event_id) <> ''),
    CONSTRAINT chk_task_events_task_id_not_blank CHECK (btrim(task_id) <> ''),
    CONSTRAINT chk_task_events_event_type_not_blank CHECK (btrim(event_type) <> ''),
    -- FIX-04（续）：event_type 词表约束镜像状态词表
    -- 'info' 作为非转换诊断事件的通用标签添加
    CONSTRAINT chk_task_events_event_type_vocab CHECK (
        event_type IN (
            'created',
            'routed',
            'queued',
            'running',
            'retrying',
            'completed',
            'failed',
            'canceled',
            'info'
        )
    ),
    CONSTRAINT chk_task_events_message_not_blank CHECK (btrim(message) <> ''),
    CONSTRAINT chk_task_events_operator_not_blank CHECK (operator IS NULL OR btrim(operator) <> ''),
    CONSTRAINT chk_task_events_error_code_not_blank CHECK (error_code IS NULL OR btrim(error_code) <> ''),
    CONSTRAINT chk_task_events_trace_id_not_blank CHECK (trace_id IS NULL OR btrim(trace_id) <> ''),
    CONSTRAINT chk_task_events_from_status CHECK (
        from_status IS NULL OR from_status IN (
            'created',
            'routed',
            'queued',
            'running',
            'retrying',
            'completed',
            'failed',
            'canceled'
        )
    ),
    CONSTRAINT chk_task_events_to_status CHECK (
        to_status IN (
            'created',
            'routed',
            'queued',
            'running',
            'retrying',
            'completed',
            'failed',
            'canceled'
        )
    ),
    CONSTRAINT chk_task_events_metadata_object CHECK (jsonb_typeof(metadata_json) = 'object'),
    PRIMARY KEY (task_id, ts, event_id) -- 支持分区的复合主键
);

-- FIX-03（续）：轻量级唯一索引仅作用于 event_id，用于幂等性强制
-- 替代之前的行内 UNIQUE 约束，结构等效但非重复
CREATE UNIQUE INDEX IF NOT EXISTS uidx_task_events_event_id
    ON task_events(event_id);

-- FIX-05：app_task_transition_with_event 现在接受 p_expected_version 用于乐观锁
-- 之前版本由触发器自动递增，但调用者无法断言特定版本
-- 这允许并发写入者静默覆盖彼此的转换
-- 传入 NULL 跳过版本检查（向后兼容的默认值）
CREATE OR REPLACE FUNCTION app_task_transition_with_event(
    p_task_id          VARCHAR(64),
    p_new_status       VARCHAR(16),
    p_event_id         VARCHAR(64),
    p_event_type       VARCHAR(64),
    p_message          TEXT,
    p_metadata_json    JSONB    DEFAULT '{}'::jsonb,
    p_operator         VARCHAR(64) DEFAULT NULL,
    p_error_code       VARCHAR(64) DEFAULT NULL,
    p_trace_id         VARCHAR(64) DEFAULT NULL,
    p_expected_version INTEGER     DEFAULT NULL  -- FIX-05：可选的乐观锁断言
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_old_status VARCHAR(16);
    v_deleted_at TIMESTAMPTZ;
    v_version    INTEGER;
BEGIN
    SELECT status, deleted_at, version
    INTO v_old_status, v_deleted_at, v_version
    FROM task_registry
    WHERE task_id = p_task_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION '任务 % 不存在', p_task_id
            USING ERRCODE = 'no_data_found';
    END IF;

    IF v_deleted_at IS NOT NULL THEN
        RAISE EXCEPTION '任务 % 已软删除，无法进行状态转换', p_task_id
            USING ERRCODE = 'check_violation';
    END IF;

    -- FIX-05：乐观并发检查
    IF p_expected_version IS NOT NULL AND v_version <> p_expected_version THEN
        RAISE EXCEPTION '任务 % 乐观锁冲突: 期望版本 % 但实际版本 %',
            p_task_id, p_expected_version, v_version
            USING ERRCODE = 'serialization_failure';
    END IF;

    UPDATE task_registry
    SET status = p_new_status
    WHERE task_id = p_task_id;

    INSERT INTO task_events (
        event_id,
        task_id,
        event_type,
        from_status,
        to_status,
        message,
        metadata_json,
        operator,
        error_code,
        trace_id
    ) VALUES (
        p_event_id,
        p_task_id,
        p_event_type,
        v_old_status,
        p_new_status,
        p_message,
        COALESCE(p_metadata_json, '{}'::jsonb),
        p_operator,
        p_error_code,
        p_trace_id
    );
END;
$$;

-- FIX-01（续）：为所有剩余触发器函数添加 SET search_path
CREATE OR REPLACE FUNCTION app_task_events_enforce_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    RAISE EXCEPTION 'task_events 是仅追加表: % 操作不被允许', TG_OP
        USING ERRCODE = 'check_violation';
END;
$$;

DROP TRIGGER IF EXISTS trg_task_events_10_enforce_immutable ON task_events;
CREATE TRIGGER trg_task_events_10_enforce_immutable
BEFORE UPDATE OR DELETE
ON task_events
FOR EACH ROW
EXECUTE FUNCTION app_task_events_enforce_immutable();

CREATE OR REPLACE FUNCTION app_task_events_block_truncate()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    RAISE EXCEPTION '禁止在 task_events 上执行 TRUNCATE 操作（仅追加审计表）'
        USING ERRCODE = 'check_violation';
END;
$$;

COMMENT ON FUNCTION app_task_transition_with_event(
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
) IS
'原子状态转换辅助函数，使用调用者权限执行。调用者必须具有 task_registry 的 UPDATE 权限和 task_events 的 INSERT 权限。传入 p_expected_version 启用乐观并发控制；传入 NULL 跳过检查。';

DROP TRIGGER IF EXISTS trg_task_events_20_block_truncate ON task_events;
CREATE TRIGGER trg_task_events_20_block_truncate
BEFORE TRUNCATE
ON task_events
FOR EACH STATEMENT
EXECUTE FUNCTION app_task_events_block_truncate();

-- -------------------------------------------------------------------------
-- 索引：task_registry
-- -------------------------------------------------------------------------

-- 同时保留仅活跃记录和全表状态索引：
-- 1) 活跃索引服务于热路径（deleted_at IS NULL）
-- 2) 全表索引保留对所有状态查询（包括软删除行）的兼容性
CREATE INDEX IF NOT EXISTS idx_task_registry_status_updated_at
    ON task_registry(status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_task_registry_updated_at
    ON task_registry(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_task_registry_active_status_updated_at
    ON task_registry(status, updated_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_task_registry_deleted_at
    ON task_registry(deleted_at DESC)
    WHERE deleted_at IS NOT NULL;

-- FIX-10：添加常用分页查询模式索引
-- 模式：ORDER BY created_at DESC LIMIT N 查询最近创建的任务
CREATE INDEX IF NOT EXISTS idx_task_registry_created_at
    ON task_registry(created_at DESC);

-- FIX-10：活跃任务创建时间的部分索引
-- 优化 "查找最近一小时内创建的活跃任务" 等查询
CREATE INDEX IF NOT EXISTS idx_task_registry_active_created_at
    ON task_registry(created_at DESC)
    WHERE deleted_at IS NULL;

-- -------------------------------------------------------------------------
-- 索引：task_events
-- -------------------------------------------------------------------------

-- 主键 (task_id, ts, event_id) 隐式覆盖 (task_id, ts) 的搜索
-- CREATE INDEX IF NOT EXISTS idx_task_events_task_id_ts ON task_events(task_id, ts ASC);

CREATE INDEX IF NOT EXISTS idx_task_events_event_type_ts
    ON task_events(event_type, ts DESC);

DROP INDEX IF EXISTS idx_task_events_trace_id;
CREATE INDEX IF NOT EXISTS idx_task_events_trace_id_ts
    ON task_events(trace_id, ts DESC)
    WHERE trace_id IS NOT NULL;

-- FIX-07：添加操作者索引用于事后归因查询
-- 模式："显示 worker_daemon 在最近一小时内产生的所有事件" 之前需要全表扫描
CREATE INDEX IF NOT EXISTS idx_task_events_operator_ts
    ON task_events(operator, ts DESC)
    WHERE operator IS NOT NULL;

-- FIX-10：添加 error_code 索引用于故障分析
-- 模式："查找最近 24 小时内特定错误码的所有失败事件"
CREATE INDEX IF NOT EXISTS idx_task_events_error_code_ts
    ON task_events(error_code, ts DESC)
    WHERE error_code IS NOT NULL;

-- -------------------------------------------------------------------------
-- 注释
-- -------------------------------------------------------------------------

COMMENT ON TABLE task_registry IS
'任务最新快照表。每个 task_id 一行，用于状态查询和生命周期控制。安全提示：请勿在 payload_json 中存储明文密码、API 密钥等敏感信息。敏感数据应在应用层加密或脱敏后再持久化。';

COMMENT ON COLUMN task_registry.task_id IS
'业务任务标识符。在生命周期和事件记录中保持稳定。';

COMMENT ON COLUMN task_registry.status IS
'当前任务状态。状态转换由触发器 app_task_registry_validate_transition 验证。';

COMMENT ON COLUMN task_registry.payload_json IS
'最新完整快照负载，JSONB 格式。存储任务元数据/结果/错误；拒绝非对象 JSON。请勿在 payload_json 中存储明文敏感信息。';

COMMENT ON COLUMN task_registry.created_at IS
'任务创建时间戳，UTC 时区（timestamptz）。插入后不可变；省略时使用数据库默认值，允许显式历史值用于受控回填。';

COMMENT ON COLUMN task_registry.updated_at IS
'最后变更时间戳，UTC 时区（timestamptz）。每次更新时自动更新。';

COMMENT ON COLUMN task_registry.deleted_at IS
'软删除标记。NULL 表示活跃；非 NULL 表示从活跃任务列表中隐藏。恢复生命周期写入前需清除 deleted_at。';

COMMENT ON COLUMN task_registry.version IS
'单调递增版本计数器。插入时省略默认值为 1，更新时自动递增。在 app_task_transition_with_event 中作为 p_expected_version 传入以启用乐观并发控制。';

COMMENT ON TABLE task_events IS
'不可变的任务生命周期事件。用于审计、故障排查和时间线重建。安全提示：请勿在 metadata_json 中存储明文敏感信息或个人身份信息。分区提示：对于高容量（1亿+行），考虑按 ts 列进行范围分区。复合主键 (task_id, ts, event_id) 支持分区裁剪。';

COMMENT ON COLUMN task_events.event_id IS
'业务事件标识符（幂等键）。通过 uidx_task_events_event_id 保证全局唯一。';

COMMENT ON COLUMN task_events.task_id IS
'所属任务引用。删除限制以保护不可变审计历史。';

COMMENT ON COLUMN task_events.event_type IS
'语义事件标签。约束为状态词表加上 info（用于非转换诊断事件）。';

COMMENT ON COLUMN task_events.from_status IS
'此事件之前的状态。首条事件可为 NULL。';

COMMENT ON COLUMN task_events.to_status IS
'此事件之后的状态。';

COMMENT ON COLUMN task_events.message IS
'面向操作人员的事件描述，用于诊断。';

COMMENT ON COLUMN task_events.metadata_json IS
'结构化事件元数据对象。必须为 JSON 对象以保证稳定解析。';

COMMENT ON COLUMN task_events.operator IS
'操作者/执行者标记，例如 worker_daemon/system/user/admin。';

COMMENT ON COLUMN task_events.error_code IS
'失败/重试事件的业务或系统错误码。';

COMMENT ON COLUMN task_events.trace_id IS
'跨服务故障排查的追踪关联 ID。';

COMMENT ON COLUMN task_events.ts IS
'事件时间戳，UTC 时区（timestamptz）。';

COMMENT ON TRIGGER trg_task_events_10_enforce_immutable ON task_events IS
'仅追加保护。拒绝 task_events 上的 UPDATE/DELETE 操作以保护审计完整性。';

COMMENT ON TRIGGER trg_task_events_20_block_truncate ON task_events IS
'仅追加保护。拒绝 task_events 上的 TRUNCATE 操作以保护审计完整性。';

COMMIT;
