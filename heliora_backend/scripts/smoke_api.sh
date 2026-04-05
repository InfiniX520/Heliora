#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TRACE_ID="trc_smoke_$(date +%s)"
IDEMPOTENCY_KEY="idem_smoke_$(date +%s)"

echo "[1/4] GET /health"
curl -fsS -H "X-Trace-Id: ${TRACE_ID}" "${BASE_URL}/health"
echo
echo

echo "[2/4] POST /api/v1/chat"
curl -fsS -X POST "${BASE_URL}/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-Trace-Id: ${TRACE_ID}" \
  -d '{"session_id":"sess_smoke","content":"hello"}'
echo
echo

echo "[3/4] POST /api/v1/memory/retrieve"
curl -fsS -X POST "${BASE_URL}/api/v1/memory/retrieve" \
  -H "Content-Type: application/json" \
  -H "X-Trace-Id: ${TRACE_ID}" \
  -d '{"query":"style","scope":"project","top_k":5}'
echo
echo

echo "[4/5] POST /api/v1/tasks/submit"
curl -fsS -X POST "${BASE_URL}/api/v1/tasks/submit" \
  -H "Content-Type: application/json" \
  -H "X-Trace-Id: ${TRACE_ID}" \
  -H "Idempotency-Key: ${IDEMPOTENCY_KEY}" \
  -d '{"task_type":"chat_assist","priority":"P2","required_capabilities":["chat"],"payload":{"content":"demo"}}'
echo
echo

echo "[5/5] POST /api/v1/tasks/consume-next"
curl -fsS -X POST "${BASE_URL}/api/v1/tasks/consume-next" \
  -H "Content-Type: application/json" \
  -H "X-Trace-Id: ${TRACE_ID}" \
  -d '{"queue":"normal.queue"}'
echo
echo

echo "Smoke tests passed against ${BASE_URL}"
