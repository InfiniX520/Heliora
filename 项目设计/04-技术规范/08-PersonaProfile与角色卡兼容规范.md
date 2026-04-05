# Heliora PersonaProfile 与角色卡兼容规范

> 文档目标: 统一本地人格配置模型、角色卡导入导出映射规则与许可证合规边界。
> 关联文档: [03-对话策略规范](../03-交互与界面/03-对话策略规范.md), [05-多智能体协同与任务分发设计](../02-架构与设计/05-多智能体协同与任务分发设计.md), [06-统一口径总索引](06-统一口径总索引.md)

---

## 1. 设计结论（本阶段）

1. 采用“本地 PersonaProfile + 外部角色卡适配器”架构。
2. 不直接接入外部前端，不复制外部项目实现代码。
3. 通过兼容角色卡公开数据格式实现导入导出能力。
4. 当前阶段仅实现接口与数据契约，不实现角色化展示增强。

---

## 2. 合规边界

### 2.1 必须遵循

1. 角色卡兼容基于公开数据格式与字段语义，不复用第三方受限代码实现。
2. 导入流程必须记录 `source`、`author`、`license`、`import_time`。
3. 对未知扩展字段执行“保留透传”，禁止静默丢弃。

### 2.2 禁止项

1. 禁止直接拷贝或改写第三方前端代码后并入本项目闭源分发。
2. 禁止删除导入卡片中的版权与来源信息（若存在）。
3. 禁止将角色卡标签字段用于策略绕过或提示词注入。

### 2.3 安全模式约束

1. 默认模式为 `strict`：角色卡不得覆盖系统安全策略。
2. 可选模式为 `trusted_local_max`：用于本地部署高权限运行，允许更高策略覆盖能力。
3. 启用 `trusted_local_max` 必须满足：本地运行、显式确认（ack）、全量审计。
4. 任意模式下都必须保留导入来源、作者与许可证元信息。

说明:
1. 本规范提供工程合规边界，不替代正式法律意见。
2. 商业分发前需完成法务复核与许可证清单归档。

---

## 3. 内部标准模型：PersonaProfile v1

### 3.1 数据结构

```json
{
  "spec": "heliora_persona_v1",
  "spec_version": "1.0",
  "id": "persona_xiling_default",
  "display_name": "曦澪",
  "description": "学习导向、清晰、克制的助教人格",
  "personality": "耐心、证据优先、最小干预",
  "scenario": "编程学习与项目答辩辅助",
  "first_message": "我们先明确目标和约束，再一步步定位。",
  "example_messages": "",
  "prompt_overrides": {
    "system_prompt": "",
    "post_history_instructions": "",
    "allow_original_placeholder": true
  },
  "greetings": {
    "alternate": []
  },
  "metadata": {
    "creator": "",
    "character_version": "",
    "tags": [],
    "source": "local",
    "license": "",
    "author": ""
  },
  "extensions": {}
}
```

### 3.2 字段约束

1. `spec` 必须为 `heliora_persona_v1`。
2. `spec_version` 当前固定为 `1.0`。
3. `extensions` 必须存在，默认 `{}`。
4. `prompt_overrides` 可为空字符串，但字段必须存在。

---

## 4. 外部角色卡兼容规则

### 4.1 支持格式

1. V1 结构（顶层字段：`name/description/personality/scenario/first_mes/mes_example`）。
2. V2 结构（`spec=chara_card_v2`，主体在 `data`）。
3. 本地导入文件类型: `.json`（P0），`.png` 内嵌卡片元数据（P1，可选开关）。

### 4.2 字段映射（导入）

| 外部字段 | PersonaProfile 字段 | 规则 |
|---|---|---|
| `name` / `data.name` | `display_name` | 必填，空值回退文件名 |
| `description` / `data.description` | `description` | 直接映射 |
| `personality` / `data.personality` | `personality` | 直接映射 |
| `scenario` / `data.scenario` | `scenario` | 直接映射 |
| `first_mes` / `data.first_mes` | `first_message` | 直接映射 |
| `mes_example` / `data.mes_example` | `example_messages` | 直接映射 |
| `data.system_prompt` | `prompt_overrides.system_prompt` | 空字符串允许 |
| `data.post_history_instructions` | `prompt_overrides.post_history_instructions` | 空字符串允许 |
| `data.alternate_greetings` | `greetings.alternate` | 非数组时置空 |
| `data.tags` | `metadata.tags` | 去重、保留原顺序 |
| `data.creator` | `metadata.creator` | 直接映射 |
| `data.character_version` | `metadata.character_version` | 字符串化 |
| `data.extensions` | `extensions` | 完整保留 |

### 4.3 未知字段策略

1. 已知字段按规范映射。
2. 未识别字段写入 `extensions["compat/raw"]`。
3. 导出时优先回填原字段，保证“导入 -> 导出”可逆。

---

## 5. 提示词拼装优先级

统一优先级如下（高到低）：

1. 系统安全与平台策略。
2. 产品对话策略（学习导向、证据优先、最小干预）。
3. PersonaProfile（含 `prompt_overrides`）。
4. 记忆注入内容（含冲突澄清规则）。
5. 用户当前输入。

约束:
1. `strict` 模式下，角色卡内容不得覆盖系统安全策略。
2. `trusted_local_max` 模式下，可允许 Persona 的 `prompt_overrides` 覆盖默认系统提示词模板。
3. 标签、作者信息不得用于提示词注入。

---

## 6. 接口契约（草案）

### 6.1 导入校验

`POST /api/v1/persona/validate-card`

请求:

```json
{
  "file_name": "xiling.json",
  "content_base64": "...",
  "format_hint": "json"
}
```

响应:

```json
{
  "trace_id": "trc_xxx",
  "ok": true,
  "detected_format": "tavern_v2",
  "warnings": []
}
```

### 6.2 导入落库

`POST /api/v1/persona/import-card`

请求:

```json
{
  "file_name": "xiling.json",
  "content_base64": "...",
  "source": "local_upload",
  "license": "",
  "author": ""
}
```

响应:

```json
{
  "trace_id": "trc_xxx",
  "persona_id": "persona_xiling_default",
  "status": "imported"
}
```

### 6.3 导出角色卡

`POST /api/v1/persona/{persona_id}/export-card`

请求:

```json
{
  "target_format": "tavern_v2"
}
```

响应:

```json
{
  "trace_id": "trc_xxx",
  "file_name": "xiling_v2.json",
  "content_base64": "..."
}
```

---

## 7. 配置与开关

建议新增配置键:

| 配置键 | 默认值 | 说明 |
|---|---:|---|
| ENABLE_PERSONA_PROFILE | true | 启用内部人格模型 |
| ENABLE_PERSONA_CARD_IMPORT | false | 启用角色卡导入 |
| ENABLE_PERSONA_CARD_EXPORT | false | 启用角色卡导出 |
| PERSONA_IMPORT_ALLOW_PNG | false | 是否允许 PNG 内嵌卡导入 |
| PERSONA_IMPORT_MAX_SIZE_MB | 5 | 导入文件体积限制 |
| SECURITY_POLICY_MODE | strict | 安全模式：strict/trusted_local_max |
| LOCAL_MAX_PRIVILEGE_ACK | false | 是否确认启用本地最高权限 |

发布策略:
1. P0 打开 `ENABLE_PERSONA_PROFILE`，其余关闭。
2. P1 灰度打开导入与校验接口。
3. P2 根据质量指标开启导出能力。
4. `trusted_local_max` 仅在本地模式和 `LOCAL_MAX_PRIVILEGE_ACK=true` 时可生效。

---

## 8. 数据与审计

建议数据对象:

1. `persona_profiles`：存储 PersonaProfile v1。
2. `persona_import_events`：记录导入来源、格式识别、告警、操作者。
3. `persona_export_events`：记录导出目标格式与时间。

审计要求:
1. 每次导入导出必须记录 `trace_id`。
2. 失败事件必须保存错误码与原始校验信息。

---

## 9. 验收标准

1. 可成功导入 V1 与 V2 两类卡片样例。
2. 未知扩展字段在导入导出后不丢失。
3. 非法输入（缺字段、超大小、伪造格式）被正确拒绝并返回错误码。
4. `strict` 模式下角色卡导入不会覆盖系统安全策略。
5. `trusted_local_max` 模式下角色卡覆盖能力按开关生效，并完整记录审计日志。
6. 本地离线模式可完成导入、校验、持久化全流程。
