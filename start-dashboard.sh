#!/usr/bin/env bash
# claudeshorts — one-shot dashboard launcher for macOS / Linux.
# Finds a Python 3.11+ interpreter, sets up a virtualenv, installs deps (Python +
# renderer), then starts the local dashboard and opens it in your browser.
# Safe to re-run any time.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT="${CLAUDESHORTS_PORT:-8000}"
URL="http://127.0.0.1:${PORT}"

# True if $1 is a runnable interpreter reporting version >= 3.11.
py_ok() {
  command -v "$1" >/dev/null 2>&1 || return 1
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,11) else 1)' \
    >/dev/null 2>&1
}

find_python() {
  local cands=()
  [ -n "${PYTHON:-}" ] && cands+=("$PYTHON")
  cands+=(python3.13 python3.12 python3.11 python3 python)
  local c
  for c in "${cands[@]}"; do
    if py_ok "$c"; then command -v "$c"; return 0; fi
  done
  return 1
}

PYBIN="$(find_python || true)"
if [ -z "$PYBIN" ]; then
  echo "✖ Python 3.11+ is required but none was found on PATH."
  echo "    macOS:  brew install python@3.12      (or download from https://www.python.org/downloads/)"
  echo "    Linux:  install python3.11+ with your package manager"
  echo "  Then double-click / re-run this launcher."
  exit 1
fi
echo "• Using $("$PYBIN" -V 2>&1) ($PYBIN)"

# (Re)create the venv if it's missing or was built with an older Python.
recreate=0
if [ -d .venv ]; then
  py_ok ".venv/bin/python" || { echo "• Existing .venv uses an old Python — recreating…"; rm -rf .venv; recreate=1; }
else
  recreate=1
fi
if [ "$recreate" -eq 1 ]; then
  echo "• Creating virtualenv (.venv)…"
  "$PYBIN" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# Install deps only if a core dependency is actually missing. (Don't probe the
# local `claudeshorts` package — it imports from the repo dir even uninstalled.)
DEPS_PROBE="import typer, fastapi, uvicorn, jinja2, anthropic, feedparser, yaml, httpx, dotenv"
if ! python -c "$DEPS_PROBE" >/dev/null 2>&1; then
  echo "• Installing Python dependencies (first run can take a minute)…"
  pip install -q --upgrade pip
  pip install -q -e .
fi

python -m claudeshorts.cli init-db >/dev/null

# Renderer deps (best-effort; the dashboard runs without them).
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
