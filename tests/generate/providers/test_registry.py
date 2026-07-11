from __future__ import annotations

import pytest

from claudeshorts.generate.providers import registry
from claudeshorts.generate.providers.claude_cli import ClaudeCLIProvider
from claudeshorts.generate.providers.claude_api import ClaudeAPIProvider
from claudeshorts.generate.providers.openai_compatible import OpenAICompatibleProvider


def test_get_provider_claude_cli():
    provider = registry.get_provider("claude_cli")
    assert isinstance(provider, ClaudeCLIProvider)


def test_get_provider_api():
    provider = registry.get_provider("api")
    assert isinstance(provider, ClaudeAPIProvider)


def test_get_provider_local():
    provider = registry.get_provider("local")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert "11434" in provider.base_url


def test_get_provider_openai_compat():
    provider = registry.get_provider("openai_compat")
    assert isinstance(provider, OpenAICompatibleProvider)


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError, match="unknown model.backend"):
        registry.get_provider("not-a-real-backend")
