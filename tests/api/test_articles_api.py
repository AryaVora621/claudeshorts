from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app


def test_add_article_pins_by_default():
    client = TestClient(create_app())
    resp = client.post("/api/v1/articles", json={"title": "Hello API"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert "job_id" not in body


def test_add_article_generate_action_returns_job_id():
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/articles", json={"title": "Hello API 2", "action": "generate"}
    )
    assert resp.status_code == 200
    assert "job_id" in resp.json()


def test_add_article_missing_title_is_422():
    client = TestClient(create_app())
    resp = client.post("/api/v1/articles", json={})
    assert resp.status_code == 422


def test_pin_unpin_article():
    client = TestClient(create_app())
    add = client.post("/api/v1/articles", json={"title": "Pin via API"}).json()
    item_id = add["item_id"]
    resp = client.post(f"/api/v1/articles/{item_id}/unpin")
    assert resp.status_code == 200
    resp = client.post(f"/api/v1/articles/{item_id}/pin")
    assert resp.status_code == 200


def test_generate_from_item_returns_job_id():
    client = TestClient(create_app())
    add = client.post("/api/v1/articles", json={"title": "Gen via API"}).json()
    resp = client.post(f"/api/v1/articles/{add['item_id']}/generate")
    assert resp.status_code == 200
    assert isinstance(resp.json()["job_id"], int)


def test_list_articles():
    client = TestClient(create_app())
    resp = client.get("/api/v1/articles")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
