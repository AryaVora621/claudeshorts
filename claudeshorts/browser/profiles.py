"""Per-profile config: browser-automation session metadata, RSS/HN/Reddit
sources, and the generation prompt all live together under
config/profiles/<slug>/ since a content profile inherently owns its own
browser session (for scraping/publishing) alongside its content identity.

Session STATE (real cookies) stays separate, under the gitignored top-level
profiles/<slug>/ — never mix it with this directory, which is safe to
review in a PR.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PROFILES_DIR = Path("config/profiles")
STATE_DIR = Path("profiles")

_DEFAULTS = {"login_health": "unknown", "browser": "chromium", "notes": ""}


def _profile_dir(slug: str) -> Path:
    return PROFILES_DIR / slug


def load_profile(slug: str) -> dict:
    path = _profile_dir(slug) / "profile.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no profile config at {path}")
    data = yaml.safe_load(path.read_text()) or {}
    return {**_DEFAULTS, **data}


def list_profiles() -> list[dict]:
    if not PROFILES_DIR.is_dir():
        return []
    slugs = sorted(p.parent.name for p in PROFILES_DIR.glob("*/profile.yaml"))
    return [{"slug": slug, **load_profile(slug)} for slug in slugs]


def load_sources(slug: str) -> list[dict]:
    path = _profile_dir(slug) / "sources.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no sources config at {path}")
    return (yaml.safe_load(path.read_text()) or {}).get("sources", [])


def load_prompt(slug: str) -> str:
    path = _profile_dir(slug) / "prompt.md"
    if not path.exists():
        raise FileNotFoundError(f"no prompt file at {path}")
    return path.read_text()


def storage_state_path(slug: str) -> Path:
    return STATE_DIR / slug / "storage_state.json"
