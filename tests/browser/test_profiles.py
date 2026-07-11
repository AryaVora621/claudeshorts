from __future__ import annotations

import pytest

from claudeshorts.browser.profiles import (
    load_profile,
    load_prompt,
    load_sources,
    list_profiles,
    storage_state_path,
)


@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    d = tmp_path / "profiles"
    d.mkdir()
    monkeypatch.setattr("claudeshorts.browser.profiles.PROFILES_DIR", d)
    return d


def _write_profile(profiles_dir, slug: str, profile_yaml: str, sources_yaml: str = "sources: []\n", prompt_md: str = "Be concise.\n"):
    d = profiles_dir / slug
    d.mkdir()
    (d / "profile.yaml").write_text(profile_yaml)
    (d / "sources.yaml").write_text(sources_yaml)
    (d / "prompt.md").write_text(prompt_md)


def test_load_profile_reads_nested_yaml(profiles_dir):
    _write_profile(profiles_dir, "fork-ai", "display_name: fork.ai\nbrowser: chromium\n")
    profile = load_profile("fork-ai")
    assert profile["display_name"] == "fork.ai"
    assert profile["browser"] == "chromium"


def test_load_profile_defaults_login_health_to_unknown(profiles_dir):
    _write_profile(profiles_dir, "fork-ai", "display_name: fork.ai\n")
    assert load_profile("fork-ai")["login_health"] == "unknown"


def test_load_profile_missing_raises_file_not_found(profiles_dir):
    with pytest.raises(FileNotFoundError):
        load_profile("no-such-profile")


def test_list_profiles_returns_all(profiles_dir):
    _write_profile(profiles_dir, "fork-ai", "display_name: fork.ai\n")
    _write_profile(profiles_dir, "midnight-curiosity", "display_name: Midnight Curiosity\n")
    slugs = {p["slug"] for p in list_profiles()}
    assert slugs == {"fork-ai", "midnight-curiosity"}


def test_list_profiles_empty_dir_returns_empty_list(profiles_dir):
    assert list_profiles() == []


def test_load_sources_reads_per_profile_sources_yaml(profiles_dir):
    _write_profile(
        profiles_dir, "fork-ai", "display_name: fork.ai\n",
        sources_yaml="sources:\n  - name: hn\n    kind: hackernews\n",
    )
    sources = load_sources("fork-ai")
    assert sources == [{"name": "hn", "kind": "hackernews"}]


def test_load_prompt_reads_per_profile_prompt_md(profiles_dir):
    _write_profile(profiles_dir, "fork-ai", "display_name: fork.ai\n", prompt_md="Be concise.\n")
    assert load_prompt("fork-ai") == "Be concise.\n"


def test_storage_state_path_under_state_dir(profiles_dir):
    from claudeshorts.browser.profiles import STATE_DIR
    assert storage_state_path("fork-ai") == STATE_DIR / "fork-ai" / "storage_state.json"
