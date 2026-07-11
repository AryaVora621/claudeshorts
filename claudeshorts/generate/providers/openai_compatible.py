"""Generic OpenAI-compatible chat-completions client. One implementation
covers every provider that speaks this de facto standard: Ollama/LM
Studio/vLLM locally (registered as `local`), and OpenRouter/NVIDIA
NIM/Gemini/OpenAI itself remotely (registered as `openai_compat`) — the
difference is only `base_url`/`api_key`/`model` in config, never new code.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class OpenAICompatibleProvider:
    def __init__(
        self, base_url: str, model: str, api_key: str | None = None,
        timeout_seconds: int = 180,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self._client = httpx.Client(timeout=timeout_seconds)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate_structured(
        self, system: str, user_prompt: str, tool_schema: dict, tool_name: str,
    ) -> dict:
        function_spec = {
            "type": "function",
            "function": {
                "name": tool_schema.get("name", tool_name),
                "description": tool_schema.get("description", ""),
                "parameters": tool_schema.get("input_schema", {"type": "object"}),
            },
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            "tools": [function_spec],
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
        }
        resp = self._client.post(
            f"{self.base_url}/chat/completions", json=body, headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        message = data["choices"][0]["message"]
        for call in message.get("tool_calls") or []:
            if call["function"]["name"] == tool_name:
                return json.loads(call["function"]["arguments"])
        raise ValueError(f"{self.base_url} response contained no {tool_name} tool call")
