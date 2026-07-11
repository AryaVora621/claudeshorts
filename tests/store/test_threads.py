from __future__ import annotations

from claudeshorts.store import db, posts, threads


def test_upsert_thread_creates_then_updates():
    with db.connect() as conn:
        tid1 = threads.upsert_thread(conn, slug="gpt-5", title="GPT-5", summary="s1", profile_id=1)
        tid2 = threads.upsert_thread(conn, slug="gpt-5", title="GPT-5 v2", summary="s2", profile_id=1)
        assert tid1 == tid2
        got = threads.get_thread_by_slug(conn, "gpt-5")
        assert got["title"] == "GPT-5 v2"


def test_open_threads_only_ongoing():
    with db.connect() as conn:
        threads.upsert_thread(conn, slug="a", title="A", summary=None, profile_id=1)
        assert len(threads.open_threads(conn, profile_id=1)) == 1


def test_link_post_thread_and_posts_for_thread():
    with db.connect() as conn:
        post_id = posts.insert_post(
            conn, item_ids=[1], title="T", slides={}, captions={}, profile_id=1,
        )
        tid = threads.upsert_thread(conn, slug="a", title="A", summary=None, profile_id=1)
        threads.link_post_thread(conn, post_id, tid)
        linked = threads.posts_for_thread(conn, tid)
        assert [p["id"] for p in linked] == [post_id]


def test_threads_with_posts_nests_posts():
    with db.connect() as conn:
        post_id = posts.insert_post(
            conn, item_ids=[1], title="T", slides={}, captions={}, profile_id=1,
        )
        tid = threads.upsert_thread(conn, slug="a", title="A", summary=None, profile_id=1)
        threads.link_post_thread(conn, post_id, tid)
        out = threads.threads_with_posts(conn)
        assert out[0]["posts"][0]["id"] == post_id


def test_open_threads_scoped_to_profile():
    with db.connect() as conn:
        threads.upsert_thread(conn, slug="a", title="A", summary=None, profile_id=1)
        threads.upsert_thread(conn, slug="b", title="B", summary=None, profile_id=2)
        assert {t["slug"] for t in threads.open_threads(conn, profile_id=1)} == {"a"}
