from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app
from claudeshorts.store import connect, posts


def _mk_post():
    with connect() as conn:
        return posts.insert_post(conn, item_ids=[1], title="T", slides={}, captions={})


def test_get_post_not_found():
    client = TestClient(create_app())
    resp = client.get("/api/v1/posts/999999")
    assert resp.status_code == 404


def test_get_post_found():
    client = TestClient(create_app())
    post_id = _mk_post()
    resp = client.get(f"/api/v1/posts/{post_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == post_id


def test_list_posts():
    client = TestClient(create_app())
    _mk_post()
    resp = client.get("/api/v1/posts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_approve_post(monkeypatch):
    client = TestClient(create_app())
    post_id = _mk_post()
    from claudeshorts.services import posts_service
    monkeypatch.setattr(posts_service, "export_post", lambda post: [])
    resp = client.post(f"/api/v1/posts/{post_id}/approve")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"post_id": post_id, "exported": True, "scheduled_for": None}


def test_approve_post_not_found():
    client = TestClient(create_app())
    resp = client.post("/api/v1/posts/999999/approve")
    assert resp.status_code == 404


def test_reject_post_with_note():
    client = TestClient(create_app())
    post_id = _mk_post()
    resp = client.post(f"/api/v1/posts/{post_id}/reject", json={"note": "meh"})
    assert resp.status_code == 200
    assert resp.json() == {"post_id": post_id}


def test_schedule_post():
    client = TestClient(create_app())
    post_id = _mk_post()
    resp = client.post(f"/api/v1/posts/{post_id}/schedule", json={"scheduled_for": "2099-01-01"})
    assert resp.status_code == 200
    assert resp.json() == {"post_id": post_id, "scheduled_for": "2099-01-01"}


def test_export_post_not_found():
    client = TestClient(create_app())
    resp = client.post("/api/v1/posts/999999/export")
    assert resp.status_code == 404
