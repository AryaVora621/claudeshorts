"""Generic OpenAI-compatible chat-completions client. One implementation
covers every provider that speaks this de facto standard: Ollama/LM
Studio/vLLM locally (registered as `local`), and OpenRouter/NVIDIA
NIM/Gemini/OpenAI itself remotely (registered as `openai_compat`) — the
difference is only `base_url`/`api_key`/`model` in config, never new code.
"""

from __future__ import annotations

import json

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
        try:
            resp = self._client.post(
                f"{self.base_url}/chat/completions", json=body, headers=self._headers(),
            )
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"could not reach {self.base_url}: request timed out. Is the local model "
                "server (Ollama/llama.cpp/LM Studio) running and responsive?"
            ) from exc
        except (httpx.ConnectError, httpx.RequestError) as exc:
            raise RuntimeError(f"could not reach {self.base_url}: {exc}") from exc
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError(
                f"{self.base_url} returned a non-JSON response body: {exc}"
            ) from exc

        choices = data.get("choices")
        if not choices or not isinstance(choices, list):
            raise RuntimeError(
                f"{self.base_url} response missing 'choices'; expected a chat-completions "
                f"object with a non-empty 'choices' list, got: {data!r}"
            )
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise RuntimeError(
                f"{self.base_url} response missing choices[0].message; got: {choices[0]!r}"
            )

        for call in message.get("tool_calls") or []:
            function = call.get("function") if isinstance(call, dict) else None
            if not isinstance(function, dict) or "name" not in function:
                raise RuntimeError(
                    f"{self.base_url} returned a malformed tool_call (missing function/name): "
                    f"{call!r}"
                )
            if function["name"] != tool_name:
                continue
            arguments = function.get("arguments")
            try:
                return json.loads(arguments)
            except (json.JSONDecodeError, TypeError) as exc:
                raise RuntimeError(
                    f"{self.base_url} returned malformed JSON for {tool_name} tool-call "
                    f"arguments: {exc}. Raw arguments: {arguments!r}"
                ) from exc
        raise ValueError(f"{self.base_url} response contained no {tool_name} tool call")
