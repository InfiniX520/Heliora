#!/usr/bin/env bash
set -euo pipefail

echo "== Containers =="
docker compose ps

echo
echo "== API health from VM (requires app running on :8000) =="
curl -fsS http://127.0.0.1:8000/health | sed 's/{/\n{/g'

echo
echo "== Worker status =="
if [ -f ".worker.pid" ]; then
	PID="$(cat .worker.pid)"
	if [ -n "${PID}" ] && kill -0 "${PID}" >/dev/null 2>&1; then
		echo "worker running, pid=${PID}"
	else
		echo "worker pid file exists but process not running"
	fi
else
	echo "worker not started"
fi

echo
echo "If this fails, start API first:"
echo "  source .venv/bin/activate && python main.py"
echo "Or start API+worker together:"
echo "  bash scripts/start_api_bg.sh"
