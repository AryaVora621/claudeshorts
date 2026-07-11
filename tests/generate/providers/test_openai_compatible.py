from __future__ import annotations

import json

import httpx
import pytest

from claudeshorts.generate.providers.openai_compatible import OpenAICompatibleProvider


def _mock_transport(response_json):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, json=response_json)
    return httpx.MockTransport(handler)


def _tool_call_response(arguments: dict):
    return {
        "choices": [{
            "message": {
                "tool_calls": [{
                    "function": {"name": "emit_post", "arguments": json.dumps(arguments)},
                }],
            },
        }],
    }


def test_generate_structured_parses_tool_call(monkeypatch):
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="qwen3")
    monkeypatch.setattr(
        provider, "_client",
        httpx.Client(transport=_mock_transport(_tool_call_response({"title": "T"}))),
    )
    result = provider.generate_structured(
        "sys", "user", {"name": "emit_post", "input_schema": {"type": "object"}}, "emit_post",
    )
    assert result == {"title": "T"}


def test_generate_structured_sends_bearer_token_when_api_key_set(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=_tool_call_response({"title": "T"}))

    provider = OpenAICompatibleProvider(
        base_url="https://openrouter.ai/api/v1", model="some/model", api_key="sk-test",
    )
    monkeypatch.setattr(provider, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    provider.generate_structured("sys", "user", {"name": "emit_post", "input_schema": {}}, "emit_post")
    assert seen["auth"] == "Bearer sk-test"


def test_generate_structured_raises_if_no_tool_call(monkeypatch):
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="qwen3")
    empty = {"choices": [{"message": {}}]}
    monkeypatch.setattr(provider, "_client", httpx.Client(transport=_mock_transport(empty)))
    with pytest.raises(ValueError, match="no emit_post tool call"):
        provider.generate_structured("sys", "user", {"name": "emit_post", "input_schema": {}}, "emit_post")
