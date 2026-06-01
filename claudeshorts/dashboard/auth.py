"""Anthropic account connection state for the dashboard Settings page.

The project supports two generation backends (see config/settings.yaml):

- ``claude_cli`` — runs under your Claude Pro/Max subscription via the ``claude``
  CLI. Login is an interactive OAuth flow, so the dashboard can only *detect*
  status and guide you to run ``claude login`` in a terminal.
- ``api`` — direct Anthropic API with an ``ANTHROPIC_API_KEY``. The key can be
  pasted in the browser; we persist it to the gitignored ``.env``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .. import config

_ENV_KEY = "ANTHROPIC_API_KEY"


def _env_path() -> Path:
    return config.ROOT / ".env"


def _key_in_env_file() -> bool:
    p = _env_path()
    if not p.exists():
        return False
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{_ENV_KEY}=") and line.split("=", 1)[1].strip():
            return True
    return False


def api_key_present() -> bool:
    return bool(os.environ.get(_ENV_KEY)) or _key_in_env_file()


def cli_path() -> str | None:
    """Absolute path to the ``claude`` CLI if it's on PATH, else None."""
    return shutil.which("claude")


def cli_logged_in() -> bool:
    """Best-effort: look for stored Claude Code credentials on the host."""
    candidates = [
        Path.home() / ".claude" / ".credentials.json",
        Path.home() / ".config" / "claude" / ".credentials.json",
        Path.home() / ".claude.json",
    ]
    return any(p.exists() for p in candidates)


def current_backend() -> str:
    return (config.settings().get("model", {}) or {}).get("backend", "claude_cli")


def status() -> dict:
    """Snapshot of connection state for rendering the Settings page."""
    backend = current_backend()
    cli = cli_path()
    has_key = api_key_present()
    logged_in = cli_logged_in()
    if backend == "api":
        ready = has_key
    else:
        ready = bool(cli) and logged_in
    return {
        "backend": backend,
        "ready": ready,
        "api_key_present": has_key,
        "cli_path": cli,
        "cli_logged_in": logged_in,
    }


def save_api_key(key: str) -> None:
    """Persist (or replace) ANTHROPIC_API_KEY in the gitignored .env file."""
    key = key.strip()
    if not key:
        raise ValueError("empty API key")
    p = _env_path()
    lines: list[str] = []
    if p.exists():
        lines = [
            ln for ln in p.read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith(f"{_ENV_KEY}=")
        ]
    lines.append(f"{_ENV_KEY}={key}")
    p.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    os.environ[_ENV_KEY] = key  # take effect without a restart


def clear_api_key() -> None:
    """Remove the stored key from .env and the current process env."""
    p = _env_path()
    if p.exists():
        lines = [
            ln for ln in p.read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith(f"{_ENV_KEY}=")
        ]
        p.write_text(("\n".join(lines).strip() + "\n") if lines else "", encoding="utf-8")
    os.environ.pop(_ENV_KEY, None)
