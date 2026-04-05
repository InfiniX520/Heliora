# 接口契约（Chat / PKG / Memory）

## 5.1 Chat

| 方法与路径 | 请求 | 成功 data | 关键错误码 |
|---|---|---|---|
| POST /api/v1/chat | session_id, content, context | message_id, content, references, memory_hits | CHAT_CONTEXT_TOO_LARGE, CHAT_MODEL_UNAVAILABLE |
| POST /api/v1/chat/stream | 同 /api/v1/chat | SSE事件流 stream_chunk/stream_done | CHAT_MODEL_UNAVAILABLE, TIMEOUT |

请求示例（POST /api/v1/chat）:
{
  "session_id": "sess_001",
  "content": "我这个空指针怎么修？",
  "context": {
    "file_path": "src/tree.py",
    "line_number": 47,
    "language": "python"
  }
}

响应示例（POST /api/v1/chat）:
{
  "code": "OK",
  "message": "success",
  "data": {
    "message_id": "msg_001",
    "content": "先看第47行对象是否初始化。",
    "references": ["concept_ds_tree_null"],
    "memory_hits": [
      {
        "memory_id": "mem_001",
        "evidence": "先给结论再细节"
      }
    ]
  },
  "trace_id": "trc_001",
  "ts": "2026-03-29T10:00:00+08:00"
}

---

## 5.2 PKG（知识图谱）

| 方法与路径 | 请求 | 成功 data | 关键错误码 |
|---|---|---|---|
| GET /api/v1/pkg/concepts | keyword, course, page, page_size | 分页概念列表 | CONCEPT_NOT_FOUND, GRAPH_INDEX_UNAVAILABLE |
| POST /api/v1/pkg/search | query, filters, top_k | concept/code/bug 混合结果 | GRAPH_QUERY_TIMEOUT, GRAPH_INDEX_UNAVAILABLE |

---

## 5.3 Memory（长期记忆）

| 方法与路径 | 请求 | 成功 data | 关键错误码 |
|---|---|---|---|
| POST /api/v1/memory/retrieve | query, scope, top_k, context | memories[], injected_context | MEMORY_SCOPE_INVALID, MEMORY_CONFLICT_PENDING |
| POST /api/v1/memory/feedback | memory_id, signal, score, session_id | accepted=true | MEMORY_NOT_FOUND, VALIDATION_ERROR |
| GET /api/v1/memory/list | scope, status, page, page_size | 分页记忆列表 | MEMORY_SCOPE_INVALID |
| PATCH /api/v1/memory/update | memory_id, op, payload | updated_memory | MEMORY_NOT_FOUND, MEMORY_VERSION_MISMATCH |
| GET /api/v1/memory/conflicts | page, page_size, max_age_hours | conflicts[] | MEMORY_NOT_FOUND |
| POST /api/v1/memory/rollback | memory_id, target_version, reason | rollback_result | MEMORY_NOT_FOUND, MEMORY_ROLLBACK_FAILED |
| DELETE /api/v1/memory/delete | memory_id, reason | delete_task_id, expected_sla_seconds | MEMORY_NOT_FOUND, MEMORY_DELETE_TIMEOUT |

请求示例（POST /api/v1/memory/retrieve）:
{
  "query": "回答风格偏好",
  "scope": "project",
  "top_k": 5,
  "context": {
    "session_id": "sess_001",
    "task_type": "chat"
  }
}

响应示例（POST /api/v1/memory/retrieve）:
{
  "code": "OK",
  "message": "success",
  "data": {
    "memories": [
      {
        "memory_id": "mem_100",
        "content": "先给结论再细节",
        "status": "active",
        "evidence": [
          {
            "turn_id": "turn_45",
            "quote": "先给结论",
            "timestamp": "2026-03-28T10:00:00+08:00"
          }
        ],
        "score": 0.83
      }
    ],
    "injected_context": "用户偏好先结论后细节。"
  },
  "trace_id": "trc_010",
  "ts": "2026-03-29T10:00:00+08:00"
}

请求示例（DELETE /api/v1/memory/delete）:
{
  "memory_id": "mem_100",
  "reason": "user_request"
}

响应示例（DELETE /api/v1/memory/delete）:
{
  "code": "ACCEPTED",
  "message": "delete accepted",
  "data": {
    "delete_task_id": "task_del_001",
    "expected_sla_seconds": 300,
    "status": "in_progress"
  },
  "trace_id": "trc_011",
  "ts": "2026-03-29T10:02:00+08:00"
}
