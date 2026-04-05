#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/5] Checking python3..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install it first: sudo apt install -y python3 python3-venv"
  exit 1
fi

echo "[2/5] Creating .venv if missing..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

echo "[3/5] Activating venv..."
source .venv/bin/activate

echo "[4/5] Installing dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "[5/5] Ensuring .env exists..."
if [ ! -f ".env" ]; then
  cp .env.example .env
fi

echo "Done. Next commands:"
echo "  source .venv/bin/activate"
echo "  pytest"
echo "  python main.py"
