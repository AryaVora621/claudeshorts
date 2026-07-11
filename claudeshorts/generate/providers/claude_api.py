"""Direct Anthropic API backend (metered ANTHROPIC_API_KEY), forced tool use.
Moved from generate/generator.py — chunk 7 extraction, no behavior change,
except tool_schema/tool_name now come from the caller instead of the
hardcoded POST_TOOL/"emit_post" constants."""

from __future__ import annotations

from typing import Any


class ClaudeAPIProvider:
    def __init__(
        self, model: str = "claude-sonnet-4-6", client: Any | None = None,
        prompt_cache: bool = True, max_tokens: int = 4096,
    ):
        self.model = model
        self._client = client
        self.prompt_cache = prompt_cache
        self.max_tokens = max_tokens

    def _client_or_default(self) -> Any:
        if self._client is not None:
            return self._client
        from anthropic import Anthropic
        return Anthropic()

    def generate_structured(
        self, system: str, user_prompt: str, tool_schema: dict, tool_name: str,
    ) -> dict:
        client = self._client_or_default()
        if self.prompt_cache:
            system_arg: Any = [{
                "type": "text", "text": system, "cache_control": {"type": "ephemeral"},
            }]
        else:
            system_arg = system
        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_arg,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user_prompt}],
        )
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                return block.input
        raise ValueError(f"Claude response contained no {tool_name} tool_use block")
