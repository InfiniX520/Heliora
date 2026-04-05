# 任务持久化系统数据库架构优化说明 (PostgreSQL)

本文档记录了对初始任务持久化系统（Day-4 PostgreSQL 迁移版本）所进行的逻辑、性能、安全与扩展性深层架构审查及优化记录。所有修改均已同步至对应 SQL 脚本中。

---

## ——— 第一轮优化（原始版本）———

## 1. 逻辑缺陷修复：完善状态机生命周期

**存在问题**：
原 `app_task_registry_validate_transition` 触发器中，任务在刚创建 (`created`) 或刚路由 (`routed`) 阶段无法流转到取消 (`canceled`) 状态，导致业务上无法终止早期任务。

**优化方案**：
增补了 `created -> canceled` 和 `routed -> canceled` 的流转许可，保证完整合规的生命周期闭环。
*修改位置*：`001_task_persistence_up.sql`

## 2. 性能极致优化：消除 MVCC 写放大 (Write Amplification)

**存在问题**：
PostgreSQL 的多版本并发控制（MVCC）机制更新数据时会全行复制。原设计中的 `app_task_registry_prepare_row` 触发器在每次高频更新任务状态时，仍会覆写庞大的 `payload_json` 字段，导致严重的表膨胀 (Table Bloat) 和 I/O 资源浪费。

**优化方案**：
移除了将外层元数据（如 `status`, `updated_at`）向内同步塞入 `payload_json` 的逻辑，实现了"动静分离更新"的第一步。后续高频状态更新将极大地减轻数据库行锁和日志生成压力。
*修改位置*：`001_task_persistence_up.sql`

## 3. 审计防抵赖与安全修复：防止历史溯源丢失

**存在问题**：
`task_events` 事件表旧的设计使用了外键级联删除 (`task_id REFERENCES task_registry(task_id) ON DELETE CASCADE`)，一旦业务系统或人为操作误删注销了 Registry 中的任务本体，其长期的流转审计事件将瞬间随之蒸发，造成合规灾难。

**优化方案**：
摘除 `ON DELETE CASCADE` 规则。现在对 `task_registry` 进行硬删除操作会直接触发外键保护报错。系统倒逼业务层采取"软删除"与历史归档方案（冷数据迁移），保护事件踪迹绝对连续、不被篡改。
*修改位置*：`001_task_persistence_up.sql`

## 4. 扩展性升级：面向海量日志表重构复合主键与分区基石

**存在问题**：
对 `task_events` 使用自增 `id BIGSERIAL` 并在后续针对 `(task_id, ts)` 设置独立索引。这在初期有效，但在半年后累积亿级事件必须做基于按时间 (`ts`) 或应用分区时，单主键将成为水平分表 `Partition` 的绊脚石，且单序列存在并发竞争点。

**优化方案**：
1. 删除物理无业务意义的 `id BIGSERIAL` 字段。
2. 引入复合主键 `PRIMARY KEY (task_id, ts, event_id)`。
3. 移除多余的单点组合索引 `idx_task_events_task_id_ts`（因 Postgres B-Tree 索引的最左前缀特性，复合主键已隐式覆盖了对这俩字段的联查需要）。
*修改位置*：`001_task_persistence_up.sql`

## 5. 验证与测试基建套件对齐

**存在问题**：
取消 `id` 列导致已有的冒烟测试与系统验证流程异常（报错 Column not found）。

**优化方案**：
更改 `002_task_persistence_verify.sql` 和 `003_task_persistence_expert_review_suite.sql` 的查表排序基准。将 `ORDER BY id ASC` 替换为更加明确的语义排序：`ORDER BY ts ASC, event_id ASC`，确保测试输出依然具有确定性。
*修改位置*：`002_task_persistence_verify.sql`, `003_task_persistence_expert_review_suite.sql`

## 6. 二次加固：阻断事件审计篡改风险（Append-Only）

**存在问题**：
`task_events` 在语义上是"不可变事件日志"，但如果没有数据库侧防护，拥有写权限的会话仍可直接 `UPDATE/DELETE` 已落库事件，导致审计链可被篡改。

**优化方案**：
新增触发器函数 `app_task_events_enforce_immutable`，并在 `task_events` 上注册 `BEFORE UPDATE OR DELETE` 触发器，统一拒绝修改和删除。
*修改位置*：`001_task_persistence_up.sql`, `001_task_persistence_down.sql`, `003_task_persistence_expert_review_suite.sql`

## 7. 二次加固：阻断 payload_json 静默降级导致的数据一致性风险

**存在问题**：
此前 `app_task_registry_prepare_row` 会把非法 `payload_json`（如数组）静默改写为 `{}`，这会掩盖上游写入缺陷并造成隐形数据丢失。

**优化方案**：
触发器改为严格校验：
1. `NULL` 自动补默认 `{}`。
2. 非对象 JSON 直接抛 `check_violation`。
这样可以在写入时及时暴露问题，避免脏数据进入主表。
*修改位置*：`001_task_persistence_up.sql`, `003_task_persistence_expert_review_suite.sql`

## 8. 二次加固：trace 诊断查询索引排序优化

**存在问题**：
常见诊断查询模式是 `WHERE trace_id = ? ORDER BY ts DESC LIMIT N`。仅有单列 `trace_id` 索引时，可能出现额外排序步骤，放大慢查询风险。

**优化方案**：
将索引升级为部分复合索引 `idx_task_events_trace_id_ts(trace_id, ts DESC) WHERE trace_id IS NOT NULL`，使过滤与排序同索引完成，提升可预测性。
*修改位置*：`001_task_persistence_up.sql`

## 9. 二次加固：关键文本标识非空约束

**存在问题**：
虽然字段是 `NOT NULL`，但仍可能写入空字符串（如 `''` 或空白字符串），导致业务主键/关联键语义退化，后续排障困难。

**优化方案**：
新增 `btrim(...) <> ''` 约束，覆盖 `task_registry.task_id` 与 `task_events` 中关键标识字段（`event_id/task_id/event_type/message` 及可选字段的非空白校验）。
*修改位置*：`001_task_persistence_up.sql`

## 10. 生命周期补边：支持失败任务重试

**存在问题**：
初版状态机将 `failed` 视为不可恢复状态，无法表达"失败后重试"的常见生产流程。

**优化方案**：
在状态机触发器中增加 `failed -> retrying` 合法流转，保持失败任务可被重试拉起。
*修改位置*：`001_task_persistence_up.sql`, `002_task_persistence_verify.sql`, `003_task_persistence_expert_review_suite.sql`

## 11. 软删除能力：保留审计链同时隐藏活跃视图

**存在问题**：
`ON DELETE RESTRICT` 虽然保护了审计历史，但业务仍需要"隐藏任务"能力，避免活跃任务列表混入历史任务。

**优化方案**：
新增 `task_registry.deleted_at`（空值表示活跃），并增加活跃任务查询部分索引：
`idx_task_registry_active_status_updated_at(status, updated_at DESC) WHERE deleted_at IS NULL`。
同时保留兼容全量查询索引。
*修改位置*：`001_task_persistence_up.sql`, `002_task_persistence_verify.sql`, `003_task_persistence_expert_review_suite.sql`, `EXPERT_DESIGN_REVIEW.md`

## 12. 安全基线补充：禁止在 payload 中明文存敏感字段

**存在问题**：
虽然结构上已限制 `payload_json` 为对象，但仍可能被误用为敏感字段明文存储容器。

**优化方案**：
在列注释与评审文档中明确安全策略：`payload_json` 不应保存明文 secrets/tokens；如业务必须保存，需在应用层做加密或脱敏后再入库。
*修改位置*：`001_task_persistence_up.sql`, `EXPERT_DESIGN_REVIEW.md`, `README.md`

## 13. 跨表一致性加固：提供原子状态迁移函数

**存在问题**：
如果应用分别执行 `UPDATE task_registry` 与 `INSERT task_events`，在异常中断或并发竞争时，可能出现"状态已变更但事件未落库"或"事件先落库但状态更新失败"的跨表不一致。

**优化方案**：
新增函数 `app_task_transition_with_event(...)`：
1. 对目标任务行 `FOR UPDATE` 加锁读取旧状态。
2. 校验软删除状态（已删除任务拒绝迁移）。
3. 在同一事务中先更新 `task_registry.status`，再插入 `task_events`。
4. 复用现有状态机触发器与事件约束，保持治理一致。
*修改位置*：`001_task_persistence_up.sql`, `001_task_persistence_down.sql`, `002_task_persistence_verify.sql`, `003_task_persistence_expert_review_suite.sql`, `EXPERT_DESIGN_REVIEW.md`

## 14. 审计防破坏加固：阻断 TRUNCATE 清空事件表

**存在问题**：
仅阻断 `UPDATE/DELETE` 仍不足以完全保护审计链，具备高权限的会话可通过 `TRUNCATE task_events` 一次性清空历史。

**优化方案**：
新增 `BEFORE TRUNCATE` 触发器 `trg_task_events_20_block_truncate`，统一抛出 `check_violation` 拒绝清空操作，补齐 append-only 审计防护闭环。
*修改位置*：`001_task_persistence_up.sql`, `001_task_persistence_down.sql`, `003_task_persistence_expert_review_suite.sql`, `EXPERT_DESIGN_REVIEW.md`

## 15. 软删除状态保护：禁止软删除任务继续流转

**存在问题**：
若只在原子函数中检查 `deleted_at`，仍可能通过直接 `UPDATE task_registry SET status=...` 绕开软删除语义，造成生命周期与业务可见性冲突。

**优化方案**：
在 `app_task_registry_validate_transition` 中增加软删除检查：当 `OLD.deleted_at IS NOT NULL` 且状态发生变化时，统一抛 `check_violation`。
同时补充专家负向测试覆盖该路径。
*修改位置*：`001_task_persistence_up.sql`, `002_task_persistence_verify.sql`, `003_task_persistence_expert_review_suite.sql`, `EXPERT_DESIGN_REVIEW.md`

## 16. 原子函数权限收敛：改为 SECURITY INVOKER

**存在问题**：
`SECURITY DEFINER` 在权限模型未明确收敛前，存在被误授予后放大写权限边界的风险。

**优化方案**：
将 `app_task_transition_with_event` 调整为 `SECURITY INVOKER`，并在函数注释与文档中明确调用者需具备 `task_registry` 更新与 `task_events` 插入权限。
*修改位置*：`001_task_persistence_up.sql`, `EXPERT_DESIGN_REVIEW.md`, `README.md`

---

## ——— 第二轮优化（深度审查新发现）———

## FIX-01. 安全漏洞修复：触发器函数缺少 search_path 保护

**存在问题（严重程度：高）**：
四个触发器函数（`app_task_registry_validate_transition`、`app_task_registry_prepare_row`、`app_task_events_enforce_immutable`、`app_task_events_block_truncate`）均未设置 `SET search_path`。
在 PostgreSQL 中，若恶意用户能在 `public` schema 下创建与系统函数同名的对象（search_path 注入），触发器执行时可能调用到被劫持的替代函数，绕过所有约束检查。
仅 `app_task_transition_with_event` 有保护，存在不一致漏洞。

**修复方案**：
对所有触发器函数统一添加 `SET search_path = pg_catalog, public`，与主函数保持一致。这是 PostgreSQL 安全编码的基础要求。
*修改位置*：`001_task_persistence_up.sql`

## FIX-02. 兼容性修复：恢复历史导入时间戳能力并增加边界校验

**存在问题（严重程度：中）**：
强制覆盖 INSERT 的 `created_at/updated_at/version` 虽然能压制伪造时间戳，但会破坏历史数据回灌场景：迁移任务无法保留原始创建时间和版本基线，审计链会失真。

**修复方案**：
将 INSERT 逻辑调整为“默认赋值 + 显式保留 + 风险边界校验”：
1. 未提供字段时，仍由 DB 赋默认值。
2. 提供字段时，保留调用方值（用于受控 backfill）。
3. 增加边界校验：禁止未来时间戳；禁止 `updated_at < created_at`。

示例：
```sql
NEW.created_at := COALESCE(NEW.created_at, now_utc);
NEW.updated_at := COALESCE(NEW.updated_at, NEW.created_at);
NEW.version    := COALESCE(NEW.version, 1);
```
*修改位置*：`001_task_persistence_up.sql`, `002_task_persistence_verify.sql`, `003_task_persistence_expert_review_suite.sql`

## FIX-03. 性能优化：消除 event_id 上的冗余双重唯一索引

**存在问题（严重程度：中）**：
`task_events.event_id` 同时有：
1. 行内 `UNIQUE` 约束 → PostgreSQL 自动创建一个独立 B-Tree 唯一索引。
2. 复合主键 `PRIMARY KEY (task_id, ts, event_id)` → 又一个 B-Tree 唯一索引，其中 event_id 作为最右列。

两个索引同时存在，每次 INSERT 都需要维护两棵 B-Tree，造成重复写放大，且对查询优化器没有额外收益。

**修复方案**：
移除行内 `UNIQUE` 约束（删除 `UNIQUE` 关键字），改为在表创建后单独建立轻量唯一索引：
```sql
CREATE UNIQUE INDEX IF NOT EXISTS uidx_task_events_event_id ON task_events(event_id);
```
idempotency 保护不变，但避免了双索引开销。
*修改位置*：`001_task_persistence_up.sql`

## FIX-04. 逻辑缺陷修复：event_type 字段缺少词表约束

**存在问题（严重程度：中）**：
`from_status` 和 `to_status` 都有枚举约束，但 `event_type` 完全是自由 VARCHAR，可写入任意字符串（如 `"RUNNING"`、`"run"`、`"RUN_TASK"` 等拼写变体），导致：
1. 审计日志语义不一致，无法可靠地按 `event_type` 聚合分析。
2. 基于 `event_type` 的索引 `idx_task_events_event_type_ts` 实际上无法被确定性地利用（扫描量不可预测）。
3. 与 `status` 字段的治理形成明显不对称。

**修复方案**：
新增约束 `chk_task_events_event_type_vocab`，将 event_type 限定为：
`created / routed / queued / running / retrying / completed / failed / canceled / info`
（`info` 为新增的通用诊断标签，用于记录不涉及状态转换的信息性事件）。
同时在专家套件中新增正/负测试覆盖（Case L / L2）。
*修改位置*：`001_task_persistence_up.sql`, `003_task_persistence_expert_review_suite.sql`

## FIX-05. 逻辑缺陷修复：乐观锁接口不完整，version 字段形同虚设

**存在问题（严重程度：中）**：
`task_registry.version` 字段由触发器自动递增，注释也说明"用于乐观并发控制"，但：
1. `app_task_transition_with_event` 函数没有 `p_expected_version` 参数，调用者无法断言"我期望任务处于版本 N"。
2. 直接 `UPDATE task_registry SET status=... WHERE task_id=...` 同样没有版本断言路径。

实际效果：两个并发 worker 同时拉到同一任务的相同版本，都发起 `running` 转换，第二个会将第一个的结果覆盖，且没有任何冲突报错。version 只能事后看出来递增了，但无法在写入时拦截竞态。

**修复方案**：
为 `app_task_transition_with_event` 新增可选参数 `p_expected_version INTEGER DEFAULT NULL`：
- 传入非 NULL 值时：在 `FOR UPDATE` 加锁后校验 `v_version = p_expected_version`，不符合则抛 `serialization_failure`。
- 传入 NULL 时：跳过校验（向后兼容，适合不需要乐观锁的写路径）。

同时更新 DOWN 脚本的函数签名（FIX-08 联动）、专家套件新增 Case I2/I3 测试。
*修改位置*：`001_task_persistence_up.sql`, `001_task_persistence_down.sql`, `003_task_persistence_expert_review_suite.sql`

## FIX-06. 查询兼容性修复：恢复全量状态查询索引

**存在问题（严重程度：低-中）**：
删除 `idx_task_registry_status_updated_at` 后，文档与测试中保留的“全量状态查询（含软删除）”路径失去专用索引，容易在数据量增长后退化为更高成本计划，同时造成文档-DDL不一致。

**修复方案**：
保留双索引策略：
1. `idx_task_registry_active_status_updated_at`：服务活跃任务热路径。
2. `idx_task_registry_status_updated_at`：服务全量状态兼容查询。

该策略用少量写放大换取查询口径稳定性和文档一致性。
*修改位置*：`001_task_persistence_up.sql`, `001_task_persistence_down.sql`, `EXPERT_DESIGN_REVIEW.md`

## FIX-07. 性能优化：补充 operator 字段索引，支持归因排查

**存在问题（严重程度：低）**：
`task_events.operator` 字段用于记录执行者身份（如 `worker_daemon / system / admin`），是事故归因的重要维度。
常见诊断查询：`WHERE operator = 'worker_daemon' ORDER BY ts DESC LIMIT N`，但该字段无索引，只能全表扫描。
在事件表行数增长到百万级后，这类查询会成为明显瓶颈。

**修复方案**：
新增部分复合索引：
```sql
CREATE INDEX IF NOT EXISTS idx_task_events_operator_ts
    ON task_events(operator, ts DESC)
    WHERE operator IS NOT NULL;
```
部分索引（`WHERE operator IS NOT NULL`）自动排除无操作者的事件，减少索引体积。
同时在专家套件 Case E 中补充对应的 EXPLAIN 验证。
*修改位置*：`001_task_persistence_up.sql`, `003_task_persistence_expert_review_suite.sql`

## FIX-08. 运维完整性：DOWN 脚本补全所有被创建对象的回滚语句

**存在问题（严重程度：低-中）**：
原 DOWN 脚本依赖 `DROP TABLE` 的级联效果来隐式删除索引，存在两个问题：
1. **意图不清晰**：阅读回滚脚本的 DBA 无法从 SQL 本身看出"索引也会被清理"，增加运维认知负担。
2. **签名过期**：`app_task_transition_with_event` 的 DROP FUNCTION 签名仍是旧版 9 参数，而新版增加了 `p_expected_version INTEGER` 第 10 个参数，会导致 DROP 静默失败（函数签名不匹配时 `DROP FUNCTION IF EXISTS` 找不到目标，函数残留）。

**修复方案**：
1. 补充所有 `DROP INDEX IF EXISTS` 语句，按创建逆序排列（先子表再父表）。
2. 更新 `app_task_transition_with_event` 的 DROP FUNCTION 签名，追加 `INTEGER` 参数类型。
3. 保留 `DROP TABLE` 用于最终清理（表本身的 drop 自然清理剩余触发器）。
*修改位置*：`001_task_persistence_down.sql`

## FIX-09. 测试套件对齐：验证脚本适配 event_type 词表约束和新函数签名

**存在问题**：
FIX-04 引入了 `chk_task_events_event_type_vocab` 约束，FIX-05 新增了 `p_expected_version` 参数，但原有验证脚本和专家套件的调用形式未更新，会在新 Schema 上出现兼容性失败。

**修复方案**：
- `002_task_persistence_verify.sql`：保持现有 event_type 值（均在词表内），添加注释说明 `p_expected_version` 省略即为 NULL（向后兼容）。
- `003_task_persistence_expert_review_suite.sql`：
  - Case A 保留”省略时间字段时 DB 默认赋值”断言（验证 FIX-02）。
  - Case A2 新增”显式历史时间与版本保留”断言（验证 FIX-02 兼容路径）。
  - Case I2/I3：新增乐观锁冲突与成功两个子测试（验证 FIX-05）。
  - Case L/L2：新增 event_type 非法词条负向测试 + `info` 类型正向测试（验证 FIX-04）。
  - Case E：新增 operator 索引的 EXPLAIN 验证（验证 FIX-07）。
*修改位置*：`002_task_persistence_verify.sql`, `003_task_persistence_expert_review_suite.sql`

---

## ——— 第三轮优化（深度安全与运维审查）———

## FIX-10. 安全加固：敏感字段存储策略与索引优化

**存在问题（严重程度：中）**：
1. **敏感字段存储风险**：虽然注释中提醒不要在 `payload_json` 中存储明文 secrets，但缺少表级别的安全注释和具体策略指引。
2. **查询模式覆盖不全**：缺少以下常见查询的优化索引：
   - 按创建时间分页查询最近创建的任务
   - 按错误码查询失败事件进行故障分析

**修复方案**：
1. **安全注释强化**：在表注释中明确添加 `SECURITY NOTE`，强调敏感字段不应以明文形式存储在 JSON 字段中。
2. **新增索引优化**：
   - `idx_task_registry_created_at`：支持按创建时间倒序的分页查询
   - `idx_task_registry_active_created_at`：支持活跃任务的创建时间查询（部分索引，排除软删除数据）
   - `idx_task_events_error_code_ts`：支持按错误码和时间排序的故障分析查询

*修改位置*：`001_task_persistence_up.sql`, `001_task_persistence_down.sql`, `EXPERT_DESIGN_REVIEW.md`

## FIX-11. 运维建议：连接池与会话管理策略

**存在问题（严重程度：低-中）**：
在高并发场景下，长连接或未正确关闭的连接可能导致连接池耗尽，影响系统可用性。

**修复方案**：
在文档中补充以下运维建议（应用层实现）：
1. **连接池配置**：
   - 推荐连接池大小：`(核心数 * 2) + 有效磁盘数`（PostgreSQL 推荐公式）
   - 设置连接超时：建议 `connect_timeout=10s`，`socket_timeout=30s`
2. **会话清理**：
   - 定期执行 `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND state_change < NOW() - INTERVAL '1 hour';` 清理空闲连接
3. **事务超时**：
   - 设置 `idle_in_transaction_session_timeout = 5min` 防止事务悬挂
   - 设置 `statement_timeout = 30s` 防止慢查询阻塞

*修改位置*：`EXPERT_DESIGN_REVIEW.md`

## FIX-12. 扩展性预留：事件表分区策略建议

**存在问题（严重程度：低）**：
当 `task_events` 表达到亿级行数时，查询性能和维护成本会显著下降。当前设计虽已预留复合主键结构支持分区，但缺少具体分区策略文档。

**修复方案**：
在表注释和文档中补充分区策略说明：
1. **分区键选择**：按 `ts` 字段的时间范围分区
2. **分区粒度建议**：按月分区（`RANGE (ts)`），适用于预计 1 亿+/年事件量的场景
3. **分区维护**：定期归档冷数据到历史表或对象存储

*修改位置*：`001_task_persistence_up.sql`, `EXPERT_DESIGN_REVIEW.md`

## FIX-13. 口径回归修正：状态机收敛到统一基线

**存在问题（严重程度：高）**：
前序评审中曾为增强灵活性放宽了部分状态迁移（如 `created/routed -> canceled`、`failed -> retrying`、`retrying -> canceled`），但与项目统一口径文档存在偏差，容易在 SQL 与运行时实现之间形成治理分叉。

**修复方案**：
将状态机严格收敛到统一口径基线：
1. `created -> routed`
2. `routed -> queued`
3. `queued -> running/canceled`
4. `running -> retrying/completed/failed/canceled`
5. `retrying -> running`
6. `completed/failed/canceled` 终态

并同步更新 verify/expert 脚本：
1. 移除 `failed -> retrying` 正向断言。
2. 增加 `failed -> retrying` 负向断言。
3. 保留 `running -> retrying -> running` 重试链路验证。

*修改位置*：`001_task_persistence_up.sql`, `002_task_persistence_verify.sql`, `003_task_persistence_expert_review_suite.sql`, `EXPERT_DESIGN_REVIEW.md`, `JUDGE_DETAILED_EXPLANATION.md`, `README.md`

---

## 已知边界（设计范围内，非缺陷）

以下问题在本阶段属于**有意识的设计边界**，不做强制修复，但在文档中明确记录：

| 编号 | 描述 | 建议后续处理 |
|------|------|-------------|
| B-01 | `payload_json` 无 GIN 索引，按 JSON 内字段过滤（如 `task_type`）会全表扫描 | 若业务频繁按 payload 内字段查询，提升为一等公民列或加 GIN 索引 |
| B-02 | 软删除后 `deleted_at` 可被清除恢复活跃，无二次保护 | 属于业务策略，在应用层控制；文档已说明"清除 deleted_at 后才能恢复写入" |
| B-03 | 重试次数无上限约束（`running <-> retrying` 可循环） | 在应用层用 `metadata_json.attempt` 计数控制；DB 层不强制以保持灵活性 |
| B-04 | 无分区策略，亿级事件后性能下降 | 后续按 `ts` 范围分区；复合主键 `(task_id, ts, event_id)` 已为分区预留结构 |
| B-05 | `from_status` 在直接 INSERT task_events 时无法与 task_registry 当前状态做一致性校验 | 生产写路径应强制通过 `app_task_transition_with_event`；直接 INSERT 仅用于测试或历史导入 |
