from __future__ import annotations

from unittest.mock import MagicMock

from claudeshorts.generate.providers.claude_api import ClaudeAPIProvider


def test_generate_structured_extracts_tool_use_block():
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit_post"
    block.input = {"title": "T"}
    message = MagicMock()
    message.content = [block]
    client = MagicMock()
    client.messages.create.return_value = message

    provider = ClaudeAPIProvider(client=client, model="claude-sonnet-4-6")
    result = provider.generate_structured(
        "sys", "user", {"name": "emit_post", "input_schema": {}}, "emit_post",
    )
    assert result == {"title": "T"}
    _, kwargs = client.messages.create.call_args
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_post"}


def test_generate_structured_raises_if_no_tool_use_block():
    message = MagicMock()
    message.content = []
    client = MagicMock()
    client.messages.create.return_value = message

    provider = ClaudeAPIProvider(client=client, model="claude-sonnet-4-6")
    import pytest
    with pytest.raises(ValueError, match="no emit_post tool_use block"):
        provider.generate_structured("sys", "user", {}, "emit_post")
