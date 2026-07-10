from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app
from claudeshorts.store import connect, posts


def _mk_post():
    with connect() as conn:
        post_id = posts.insert_post(
            conn, item_ids=[1], title="T", slides={}, captions={}
        )
        conn.commit()
        return post_id


def test_approve_redirects_with_message(monkeypatch):
    client = TestClient(create_app())
    post_id = _mk_post()
    from claudeshorts.services import posts_service
    monkeypatch.setattr(posts_service, "export_post", lambda post: [])
    resp = client.post(f"/posts/{post_id}/approve", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert "/review" in resp.headers["location"]


def test_export_and_publish_now_both_use_export_post_now(monkeypatch):
    client = TestClient(create_app())
    post_id = _mk_post()
    calls = []
    from claudeshorts.services import posts_service
    monkeypatch.setattr(
        posts_service, "export_post", lambda post: calls.append(post["id"]) or []
    )
    client.post(f"/posts/{post_id}/export", follow_redirects=False)
    client.post(f"/posts/{post_id}/publish-now", follow_redirects=False)
    assert calls == [post_id, post_id]


def test_approve_when_export_raises_filenotfounderror(monkeypatch):
    """Regression: approve should catch FileNotFoundError from export and redirect with err."""
    client = TestClient(create_app())
    post_id = _mk_post()
    from claudeshorts.services import posts_service

    def raise_filenotfound(post):
        raise FileNotFoundError("missing render")

    monkeypatch.setattr(posts_service, "export_post", raise_filenotfound)
    resp = client.post(f"/posts/{post_id}/approve", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    location = resp.headers["location"]
    assert "/review" in location
    assert "err=" in location
    assert "missing" in location  # URL-encoded: "missing+render"


def test_schedule_nonexistent_post_redirects_with_error():
    """Regression: scheduling a nonexistent post should redirect with error, not 500."""
    client = TestClient(create_app())
    resp = client.post(
        "/posts/999999/schedule",
        data={"scheduled_for": "2026-07-15"},
        follow_redirects=False
    )
    assert resp.status_code in (302, 303, 307)
    location = resp.headers["location"]
    assert "err=" in location
