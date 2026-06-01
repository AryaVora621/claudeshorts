#!/usr/bin/env bash
# claudeshorts — one-shot dashboard launcher for macOS / Linux.
# Sets up a virtualenv, installs deps (Python + renderer), then starts the
# local dashboard and opens it in your browser. Re-run it any time.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT="${CLAUDESHORTS_PORT:-8000}"
PY="${PYTHON:-python3}"
URL="http://127.0.0.1:${PORT}"

command -v "$PY" >/dev/null 2>&1 || { echo "✖ Python 3.11+ is required (not found on PATH)."; exit 1; }

if [ ! -d .venv ]; then
  echo "• Creating virtualenv (.venv)…"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import claudeshorts" >/dev/null 2>&1; then
  echo "• Installing Python dependencies…"
  pip install -q --upgrade pip
  pip install -q -e .
fi

python -m claudeshorts.cli init-db >/dev/null

if command -v node >/dev/null 2>&1; then
  if [ -f renderer/package.json ] && [ ! -d renderer/node_modules ]; then
    echo "• Installing renderer dependencies (npm)…"
    ( cd renderer && npm install --silent ) || echo "  ⚠ npm install failed — video rendering may not work yet."
  fi
else
  echo "  ⚠ Node.js not found — the dashboard runs, but video rendering needs Node (see renderer/)."
fi

# Open the browser shortly after the server starts.
( sleep 2
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  fi ) >/dev/null 2>&1 &

echo ""
echo "▶ claudeshorts dashboard → $URL   (press Ctrl-C to stop)"
exec python -m claudeshorts.cli serve --port "$PORT"
