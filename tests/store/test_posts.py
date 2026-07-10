from __future__ import annotations

from claudeshorts.store import db, posts


def _mk(conn, **overrides):
    kwargs = dict(item_ids=[1, 2], title="T", slides={"a": 1}, captions={"b": 2})
    kwargs.update(overrides)
    return posts.insert_post(conn, **kwargs)


def test_insert_and_get_post_round_trips_json():
    with db.connect() as conn:
        post_id = _mk(conn)
        got = posts.get_post(conn, post_id)
        assert got["item_ids"] == [1, 2]
        assert got["slides"] == {"a": 1}
        assert got["captions"] == {"b": 2}
        assert got["status"] == "draft"


def test_status_counts_and_posts_by_status():
    with db.connect() as conn:
        _mk(conn)
        p2 = _mk(conn)
        posts.set_status(conn, p2, "approved")
        counts = posts.status_counts(conn)
        assert counts == {"draft": 1, "approved": 1}
        approved = posts.posts_by_status(conn, "approved")
        assert [p["id"] for p in approved] == [p2]


def test_schedule_and_due_posts():
    with db.connect() as conn:
        p1 = _mk(conn)
        posts.set_status(conn, p1, "approved")
        posts.set_schedule(conn, p1, "2020-01-01")
        assert [p["id"] for p in posts.scheduled_posts(conn)] == [p1]
        assert [p["id"] for p in posts.due_posts(conn, "2099-01-01")] == [p1]
        assert posts.due_posts(conn, "2000-01-01") == []


def test_used_item_ids_aggregates_recent_posts():
    with db.connect() as conn:
        _mk(conn, item_ids=[10, 20])
        _mk(conn, item_ids=[20, 30])
        assert posts.used_item_ids(conn, days=1) == {10, 20, 30}


def test_recent_posts_and_all_posts():
    with db.connect() as conn:
        _mk(conn)
        _mk(conn)
        assert len(posts.recent_posts(conn, days=1)) == 2
        assert len(posts.all_posts(conn, limit=200)) == 2
