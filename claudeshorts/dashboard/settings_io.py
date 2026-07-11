"""Read/write config/settings.yaml from the dashboard.

Persists operator tweaks (backend, posts-per-day, audio mode, platforms) and
invalidates the cached ``config.settings()`` so the change takes effect without
a restart.

Note: saving rewrites settings.yaml via PyYAML, which drops the inline comments
the file ships with. The Settings page warns about this. Editing the file by
hand remains fully supported.
"""

from __future__ import annotations

from typing import Any

import yaml

from .. import config


def load() -> dict[str, Any]:
    """Fresh parse of settings.yaml (bypasses the lru_cache)."""
    return config._load_yaml(config.SETTINGS_PATH)


def _deep_merge(base: dict, updates: dict) -> dict:
    for key, val in updates.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


def save(data: dict[str, Any]) -> None:
    with config.SETTINGS_PATH.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
    config.settings.cache_clear()  # next settings() reads the new file


def update(updates: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``updates`` into settings.yaml and persist."""
    data = load()
    _deep_merge(data, updates)
    save(data)
    return data


def set_backend(backend: str) -> None:
    if backend not in ("claude_cli", "api", "local", "openai_compat"):
        raise ValueError(f"unknown backend {backend!r}")
    update({"model": {"backend": backend}})
