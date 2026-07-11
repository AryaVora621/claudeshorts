"""Profile metadata (config/profiles/<slug>.yaml, versionable) is kept
separate from session state (profiles/<slug>/storage_state.json,
gitignored, holds real cookies) — metadata is safe to review in a PR,
session state never should be."""

from __future__ import annotations

from pathlib import Path

import yaml

PROFILES_DIR = Path("config/profiles")
STATE_DIR = Path("profiles")

_DEFAULTS = {"login_health": "unknown", "browser": "chromium", "notes": ""}


def load_profile(slug: str) -> dict:
    path = PROFILES_DIR / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no profile config at {path}")
    data = yaml.safe_load(path.read_text()) or {}
    return {**_DEFAULTS, **data}


def list_profiles() -> list[dict]:
    if not PROFILES_DIR.is_dir():
        return []
    return [load_profile(p.stem) for p in sorted(PROFILES_DIR.glob("*.yaml"))]


def storage_state_path(slug: str) -> Path:
    return STATE_DIR / slug / "storage_state.json"
