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
