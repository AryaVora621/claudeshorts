"""Project paths and config loading.

Centralizes filesystem layout and YAML config access so every subsystem agrees
on where things live. Runtime dirs (data/, review/, publish/, renders/) are
created on demand and are gitignored.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import yaml

# Repo root = parent of this package directory.
ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
REVIEW_DIR = ROOT / "review"
PUBLISH_DIR = ROOT / "publish"
RENDERS_DIR = ROOT / "renders"
RENDERER_DIR = ROOT / "renderer"

DB_PATH = DATA_DIR / "app.db"

SETTINGS_PATH = CONFIG_DIR / "settings.yaml"
SOURCES_PATH = CONFIG_DIR / "profiles" / "fork-ai" / "sources.yaml"


def ensure_dirs() -> None:
    """Create runtime directories if they don't exist yet."""
    for d in (DATA_DIR, REVIEW_DIR, PUBLISH_DIR, RENDERS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@functools.lru_cache(maxsize=1)
def settings() -> dict[str, Any]:
    """Parsed config/settings.yaml (cached)."""
    return _load_yaml(SETTINGS_PATH)


@functools.lru_cache(maxsize=1)
def sources() -> list[dict[str, Any]]:
    """List of configured news sources from config/sources.yaml (cached)."""
    return _load_yaml(SOURCES_PATH).get("sources", [])


def supabase_db_url() -> str:
    """The Supabase Postgres connection string (Session Pooler), from env."""
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError(
            "SUPABASE_DB_URL is not set. Copy .env.example to .env and fill "
            "in the Session Pooler connection string from your Supabase "
            "project's Database settings."
        )
    return url
