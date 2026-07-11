from __future__ import annotations

import pytest

from claudeshorts.services import posts_service
from claudeshorts.store import connect, insert_post, set_schedule


def _mk_post(**overrides):
    kwargs = dict(item_ids=[1], title="T", slides={"a": 1}, captions={"b": 2})
    kwargs.update(overrides)
    with connect() as conn:
        return posts_service_test_insert(conn, kwargs)


def posts_service_test_insert(conn, kwargs):
    from claudeshorts.store import posts
    return posts.insert_post(conn, **kwargs)


def test_approve_post_not_found_raises():
    with pytest.raises(ValueError, match="not found"):
        posts_service.approve_post(999999)


def test_approve_post_without_schedule_exports_immediately(monkeypatch):
    post_id = _mk_post()
    called = {}

    def fake_export(post):
        called["post_id"] = post["id"]
        return []

    monkeypatch.setattr(posts_service, "export_post", fake_export)
    result = posts_service.approve_post(post_id)
    assert result == {"post_id": post_id, "exported": True, "scheduled_for": None}
    assert called["post_id"] == post_id
    with connect() as conn:
        from claudeshorts.store import get_post
        assert get_post(conn, post_id)["status"] == "approved"


def test_approve_post_with_schedule_does_not_export(monkeypatch):
    post_id = _mk_post()
    with connect() as conn:
        set_schedule(conn, post_id, "2099-01-01")
    monkeypatch.setattr(
        posts_service, "export_post",
        lambda post: (_ for _ in ()).throw(AssertionError("should not export")),
    )
    result = posts_service.approve_post(post_id)
    assert result == {"post_id": post_id, "exported": False, "scheduled_for": "2099-01-01"}


def test_reject_post_sets_status_and_note():
    post_id = _mk_post()
    posts_service.reject_post(post_id, note="not good enough")
    with connect() as conn:
        from claudeshorts.store import get_post
        got = get_post(conn, post_id)
    assert got["status"] == "rejected"
    assert got["review_note"] == "not good enough"


def test_schedule_post_sets_and_clears():
    post_id = _mk_post()
    posts_service.schedule_post(post_id, "2099-06-01")
    with connect() as conn:
        from claudeshorts.store import get_post
        assert get_post(conn, post_id)["scheduled_for"] == "2099-06-01"
    posts_service.schedule_post(post_id, None)
    with connect() as conn:
        from claudeshorts.store import get_post
        assert get_post(conn, post_id)["scheduled_for"] is None


def test_export_post_now_not_found_raises():
    with pytest.raises(ValueError, match="not found"):
        posts_service.export_post_now(999999)


def test_list_posts_returns_inserted_post():
    post_id = _mk_post()
    result = posts_service.list_posts()
    assert any(p["id"] == post_id for p in result)


def test_get_post_not_found_raises():
    with pytest.raises(ValueError, match="not found"):
        posts_service.get_post(999999)


def test_get_post_returns_post():
    post_id = _mk_post()
    result = posts_service.get_post(post_id)
    assert result["id"] == post_id


def test_export_post_now_approves_and_exports(monkeypatch):
    post_id = _mk_post()
    called = {}
    monkeypatch.setattr(
        posts_service, "export_post",
        lambda post: called.setdefault("post_id", post["id"]) or [],
    )
    result = posts_service.export_post_now(post_id)
    assert result == {"post_id": post_id}
    assert called["post_id"] == post_id
    with connect() as conn:
        from claudeshorts.store import get_post
        assert get_post(conn, post_id)["status"] == "approved"
