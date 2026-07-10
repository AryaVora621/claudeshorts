#!/usr/bin/env bash
# claudeshorts — one-shot dashboard launcher for macOS / Linux.
# Finds a Python 3.11+ interpreter, sets up a virtualenv, installs deps (Python +
# renderer), then starts the local dashboard and opens it in your browser.
# Safe to re-run any time.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Double-click launches and some terminal integrations do not load the user's
# shell profile. Add the standard macOS local install paths before probing tools.
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"

# Bind address: default to all interfaces so the dashboard is reachable from
# other devices on your LAN (the desktop / home-server use case). Set
# CLAUDESHORTS_HOST=127.0.0.1 to restrict it to this machine only.
HOST="${CLAUDESHORTS_HOST:-0.0.0.0}"
PORT="${CLAUDESHORTS_PORT:-8000}"
URL="http://127.0.0.1:${PORT}"   # the browser we auto-open is always local

# Best-effort LAN IP for the "reachable from other devices" URL we print.
lan_ip() {
  local ip=""
  if command -v ip >/dev/null 2>&1; then
    ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')" || ip=""
  fi
  if [ -z "$ip" ] && command -v hostname >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1; exit}')" || ip=""
  fi
  if [ -z "$ip" ] && command -v ipconfig >/dev/null 2>&1; then
    local i
    for i in en0 en1 en2 en3; do
      ip="$(ipconfig getifaddr "$i" 2>/dev/null)" || ip=""
      [ -n "$ip" ] && break
    done
  fi
  printf '%s' "$ip"
}

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
  # Finder and some terminal launchers start with a tiny PATH, so python.org
  # or Homebrew installs can be present but invisible to command -v.
  cands+=(.venv/bin/python)
  cands+=(/opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11)
  cands+=(/usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11)
  cands+=(/Library/Frameworks/Python.framework/Versions/Current/bin/python3)
  cands+=(/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13)
  cands+=(/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12)
  cands+=(/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11)
  local c
  for c in "${cands[@]}"; do
    if py_ok "$c"; then
      if [[ "$c" == */* ]]; then
        printf '%s\n' "$c"
      else
        command -v "$c"
      fi
      return 0
    fi
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

# True if the existing venv is usable from this repo path.
venv_ok() {
  [ -x .venv/bin/python ] || return 1
  py_ok ".venv/bin/python" || return 1
  ".venv/bin/python" -m pip -V >/dev/null 2>&1 || return 1
  [ -x .venv/bin/pip ] || return 1
  ".venv/bin/pip" -V >/dev/null 2>&1 || return 1
}

# (Re)create the venv if it's missing, old, or still points at a moved checkout.
recreate=0
if [ -d .venv ]; then
  venv_ok || { echo "• Existing .venv is old or moved - recreating..."; rm -rf .venv; recreate=1; }
else
  recreate=1
fi
if [ "$recreate" -eq 1 ]; then
  echo "• Creating virtualenv (.venv)…"
  "$PYBIN" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
VENV_PYTHON="$ROOT/.venv/bin/python"

# Install deps only if a core dependency is actually missing. (Don't probe the
# local `claudeshorts` package — it imports from the repo dir even uninstalled.)
DEPS_PROBE="import typer, fastapi, uvicorn, jinja2, anthropic, feedparser, yaml, httpx, dotenv"
if ! "$VENV_PYTHON" -c "$DEPS_PROBE" >/dev/null 2>&1; then
  echo "• Installing Python dependencies (first run can take a minute)…"
  "$VENV_PYTHON" -m pip install -q --upgrade pip setuptools wheel
  "$VENV_PYTHON" -m pip install -q -e .
fi

"$VENV_PYTHON" -m claudeshorts.cli init-db >/dev/null

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
echo "▶ claudeshorts dashboard   (press Ctrl-C to stop)"
echo "    local:  $URL"
if [ "$HOST" = "0.0.0.0" ]; then
  LANIP="$(lan_ip)"
  if [ -n "$LANIP" ]; then
    echo "    LAN:    http://${LANIP}:${PORT}   (open this from other devices on your network)"
  fi
  echo "    note:   listening on all interfaces; set CLAUDESHORTS_HOST=127.0.0.1 to keep it local-only."
fi
exec "$VENV_PYTHON" -m claudeshorts.cli serve --host "$HOST" --port "$PORT"
