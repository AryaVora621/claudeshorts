"""Maps a `model.backend` config string to a live provider instance. Reads
config lazily per call (matching the rest of the codebase's `settings()`
pattern) so a settings.yaml edit takes effect without a restart-sensitive
module-level cache.
"""

from __future__ import annotations

import os
from typing import Any

from ...config import settings
from .claude_api import ClaudeAPIProvider
from .claude_cli import ClaudeCLIProvider
from .openai_compatible import OpenAICompatibleProvider


def get_provider(name: str, *, client: Any | None = None, model: str | None = None):
    cfg = settings().get("model", {})
    if name == "claude_cli":
        return ClaudeCLIProvider(
            cli_model=cfg.get("cli_model", "sonnet"),
            timeout_seconds=cfg.get("timeout_seconds", 180),
        )
    if name == "api":
        return ClaudeAPIProvider(
            model=model or cfg.get("name", "claude-sonnet-4-6"),
            client=client,
            prompt_cache=cfg.get("prompt_cache", True),
            max_tokens=cfg.get("max_tokens", 4096),
        )
    if name == "local":
        local_cfg = cfg.get("local", {})
        return OpenAICompatibleProvider(
            base_url=local_cfg.get("base_url", "http://127.0.0.1:11434/v1"),
            model=local_cfg.get("model", ""),
        )
    if name == "openai_compat":
        oc_cfg = cfg.get("openai_compat", {})
        return OpenAICompatibleProvider(
            base_url=oc_cfg.get("base_url", ""),
            model=oc_cfg.get("model", ""),
            api_key=os.environ.get(oc_cfg.get("api_key_env", "OPENAI_COMPAT_API_KEY")),
        )
    raise ValueError(f"unknown model.backend: {name!r} (use claude_cli|api|local|openai_compat)")
