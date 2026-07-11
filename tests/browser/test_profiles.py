from __future__ import annotations

import pytest

import claudeshorts.browser.profiles as profiles_mod
from claudeshorts.browser import profiles


def test_load_profile_reads_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    (tmp_path / "acme-youtube.yaml").write_text(
        "slug: acme-youtube\nplatform: youtube\nlogin_health: ok\n"
    )
    profile = profiles.load_profile("acme-youtube")
    assert profile["platform"] == "youtube"
    assert profile["login_health"] == "ok"


def test_load_profile_defaults_login_health_to_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    (tmp_path / "acme-tiktok.yaml").write_text("slug: acme-tiktok\nplatform: tiktok\n")
    profile = profiles.load_profile("acme-tiktok")
    assert profile["login_health"] == "unknown"


def test_load_profile_missing_raises_file_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        profiles.load_profile("does-not-exist")


def test_list_profiles_returns_all(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    (tmp_path / "a.yaml").write_text("slug: a\nplatform: youtube\n")
    (tmp_path / "b.yaml").write_text("slug: b\nplatform: tiktok\n")
    slugs = sorted(p["slug"] for p in profiles.list_profiles())
    assert slugs == ["a", "b"]


def test_list_profiles_empty_dir_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    assert profiles.list_profiles() == []


def test_storage_state_path_under_state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "STATE_DIR", tmp_path)
    path = profiles.storage_state_path("acme-youtube")
    assert path == tmp_path / "acme-youtube" / "storage_state.json"
