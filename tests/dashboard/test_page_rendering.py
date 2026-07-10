"""Regression tests: every page that lists rows with DB timestamp columns.

Postgres (psycopg3) returns TIMESTAMPTZ columns as `datetime.datetime`, not the
ISO strings SQLite used to hand back. Templates that string-sliced those values
(e.g. ``(p.created_at or '')[:16]``) 500'd once populated with a real row —
GET /posts only failed once a post existed to render. These tests always seed
at least one row in the relevant table before hitting the route, so an empty
table can't hide a broken template.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app
from claudeshorts.store import connect, items, posts, set_status
from claudeshorts.store import threads as threads_store
from claudeshorts.store.runs import start_run, finish_run
from claudeshorts.jobs import queue as job_queue


def _mk_post(**kw):
    with connect() as conn:
        post_id = posts.insert_post(
            conn, item_ids=[1], title="T", slides={}, captions={}, **kw
        )
        conn.commit()
        return post_id


def test_overview_renders_with_a_run_and_job(monkeypatch):
    job_queue.enqueue("ingest", {}, name="test job")
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200


def test_posts_page_renders_with_a_post():
    _mk_post()
    client = TestClient(create_app())
    resp = client.get("/posts")
    assert resp.status_code == 200
    assert "T" in resp.text


def test_schedule_page_renders_with_a_scheduled_post():
    post_id = _mk_post(status="approved")
    with connect() as conn:
        posts.set_schedule(conn, post_id, "2026-08-01")
        conn.commit()
    client = TestClient(create_app())
    resp = client.get("/schedule")
    assert resp.status_code == 200


def test_review_page_renders_with_a_rendered_post():
    post_id = _mk_post()
    with connect() as conn:
        set_status(conn, post_id, "rendered")
        conn.commit()
    client = TestClient(create_app())
    resp = client.get("/review")
    assert resp.status_code == 200


def test_articles_page_renders_with_an_item():
    with connect() as conn:
        items.insert_item(conn, {
            "source": "test", "url": "http://example.com", "title": "hello",
            "summary": "sum", "published_at": None, "content_hash": "abc123",
        })
        conn.commit()
    client = TestClient(create_app())
    resp = client.get("/articles")
    assert resp.status_code == 200
    assert "hello" in resp.text


def test_jobs_page_renders_with_a_job():
    job_queue.enqueue("ingest", {}, name="test job")
    client = TestClient(create_app())
    resp = client.get("/jobs")
    assert resp.status_code == 200


def test_threads_page_renders_with_a_thread_and_post():
    post_id = _mk_post()
    with connect() as conn:
        thread_id = threads_store.upsert_thread(
            conn, slug="test-thread", title="Test Thread", summary=None
        )
        threads_store.link_post_thread(conn, post_id, thread_id)
        conn.commit()
    client = TestClient(create_app())
    resp = client.get("/threads")
    assert resp.status_code == 200
    assert "test-thread" in resp.text


def test_runs_page_renders_with_a_run():
    with connect() as conn:
        run_id = start_run(conn, "2026-07-11")
        finish_run(conn, run_id, status="ok", posts_created=1, detail="")
        conn.commit()
    client = TestClient(create_app())
    resp = client.get("/runs")
    assert resp.status_code == 200
