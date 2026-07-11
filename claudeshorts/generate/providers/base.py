"""The shared interface every LLM provider implements — goal.md: never
hardcode providers, always code against an interface. `tool_schema`/
`tool_name` describe the structured output every caller wants; each
provider is responsible for whatever mechanism its backend uses to
enforce that shape (Claude's forced tool_choice, OpenAI-compatible
function calling, etc.)."""

from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    def generate_structured(
        self, system: str, user_prompt: str, tool_schema: dict, tool_name: str,
    ) -> dict: ...
