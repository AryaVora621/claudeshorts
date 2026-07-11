from __future__ import annotations

from unittest.mock import patch

import pytest

from claudeshorts.generate import generator


def _valid_post() -> dict:
    return {
        "title": "Big AI news",
        "thread_slug": "big-ai-news",
        "thread_title": "Big AI News",
        "thread_summary": "Something happened.",
        "theme": {
            "subject": "OpenAI", "mood": "dark",
            "primary": "#000000", "secondary": "#111111", "accent": "#222222",
        },
        "slides": [
            {"headline": "Hook", "bullets": ["a"]},
            {"headline": "Body", "bullets": ["b"]},
            {"headline": "Takeaway", "bullets": ["c"]},
        ],
        "captions": {
            "youtube": {"title": "t", "description": "d", "hashtags": ["#ai"]},
            "tiktok": {"caption": "c", "hashtags": ["#ai"]},
            "instagram": {"caption": "c", "hashtags": ["#ai"]},
        },
    }


class _FakeProvider:
    def __init__(self, result: dict):
        self._result = result
        self.calls: list[tuple] = []

    def generate_structured(self, system, user_prompt, tool_schema, tool_name):
        self.calls.append((system, user_prompt, tool_schema, tool_name))
        return self._result


def test_generate_post_dispatches_to_configured_backend():
    item = {"source": "TechCrunch", "title": "GPT-5 launches", "url": "http://x", "summary": "s"}
    fake = _FakeProvider(_valid_post())
    with patch("claudeshorts.generate.generator.registry.get_provider", return_value=fake) as get_provider:
        result = generator.generate_post(item, backend="api")
    get_provider.assert_called_once()
    args, kwargs = get_provider.call_args
    assert args[0] == "api"
    assert result["title"] == "Big AI news"
    # api backend gets the plain user prompt, not the CLI's schema-in-text form
    assert fake.calls[0][1] == generator.build_user_prompt(item)


def test_generate_post_uses_cli_prompt_for_claude_cli_backend():
    item = {"source": "TechCrunch", "title": "GPT-5 launches", "url": "http://x", "summary": "s"}
    fake = _FakeProvider(_valid_post())
    with patch("claudeshorts.generate.generator.registry.get_provider", return_value=fake):
        generator.generate_post(item, backend="claude_cli")
    assert fake.calls[0][1] == generator.build_cli_prompt(item)


def test_generate_post_defaults_backend_from_settings():
    item = {"source": "TechCrunch", "title": "GPT-5 launches", "url": "http://x", "summary": "s"}
    fake = _FakeProvider(_valid_post())
    with patch("claudeshorts.generate.generator.registry.get_provider", return_value=fake) as get_provider, \
         patch("claudeshorts.generate.generator.settings", return_value={"model": {"backend": "local"}}):
        generator.generate_post(item)
    assert get_provider.call_args[0][0] == "local"


def test_generate_post_raises_valueerror_on_invalid_post():
    item = {"source": "TechCrunch", "title": "GPT-5 launches", "url": "http://x", "summary": "s"}
    bad = _valid_post()
    del bad["title"]  # violates schema.validate_post
    fake = _FakeProvider(bad)
    with patch("claudeshorts.generate.generator.registry.get_provider", return_value=fake):
        with pytest.raises(ValueError, match="invalid post from model"):
            generator.generate_post(item, backend="api")
