# SLA/SLO 统一

| 指标 | 目标值 | 归属模块 |
|---|---|---|
| 删除请求闭环SLA | <= 5分钟 | Memory Service |
| 错误记忆回滚 | <= 5分钟 | Memory Service |
| 冲突未决时长 | 单条 <= 24小时 | Memory Service + HITL |
| 实时队列SLA | <= 3000ms | realtime.queue |
| 记忆队列SLA | <= 5000ms | memory.queue |
| 普通队列SLA | <= 15000ms | normal.queue |
| 批处理队列SLA | <= 300000ms | batch.queue |
| 对话首字延迟增量 | P95 <= 120ms | Chat + Memory Retrieve |
| 删除链路审计覆盖率 | 100% | memory_events |