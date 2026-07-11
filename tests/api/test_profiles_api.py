from __future__ import annotations

from fastapi.testclient import TestClient

import claudeshorts.browser.profiles as profiles_mod
from claudeshorts.dashboard import create_app


def test_get_profiles_returns_list(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    (tmp_path / "acme-youtube.yaml").write_text(
        "slug: acme-youtube\nplatform: youtube\nlogin_health: ok\n"
    )
    client = TestClient(create_app())
    resp = client.get("/api/v1/profiles")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [{"slug": "acme-youtube", "platform": "youtube", "login_health": "ok"}]


def test_get_profiles_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    client = TestClient(create_app())
    resp = client.get("/api/v1/profiles")
    assert resp.status_code == 200
    assert resp.json() == []
