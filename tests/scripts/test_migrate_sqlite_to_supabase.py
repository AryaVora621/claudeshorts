from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from claudeshorts.store import db
from scripts.migrate_sqlite_to_supabase import main


def _make_source_db(tmp_path: Path) -> Path:
    path = tmp_path / "source.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, source TEXT, url TEXT, "
        "title TEXT, summary TEXT, published_at TEXT, content_hash TEXT, "
        "fetched_at TEXT)"
    )
    conn.execute(
        "INSERT INTO items (id, source, url, title, summary, published_at, "
        "content_hash, fetched_at) VALUES "
        "(1, 'test', 'https://a', 'Title', 'sum', NULL, 'hash-1', '2026-01-01')"
    )
    conn.execute(
        "CREATE TABLE posts (id INTEGER PRIMARY KEY, item_ids TEXT, status TEXT, "
        "title TEXT, slides_json TEXT, theme_json TEXT, captions_json TEXT, "
        "review_note TEXT, published_at TEXT, scheduled_for TEXT, created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO posts (id, item_ids, status, title, slides_json, "
        "theme_json, captions_json, review_note, published_at, scheduled_for, "
        "created_at) VALUES "
        "(1, '[1]', 'draft', 'Post One', '{\"a\": 1}', NULL, NULL, NULL, "
        "NULL, NULL, '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO posts (id, item_ids, status, title, slides_json, "
        "theme_json, captions_json, review_note, published_at, scheduled_for, "
        "created_at) VALUES "
        "(2, '[1]', 'published', 'Post Two', '{\"a\": 1}', NULL, NULL, NULL, "
        "NULL, NULL, '2026-01-02')"
    )
    conn.execute(
        "CREATE TABLE threads (id INTEGER PRIMARY KEY, slug TEXT, title TEXT, "
        "summary TEXT, status TEXT, first_seen TEXT, last_updated TEXT)"
    )
    conn.execute(
        "INSERT INTO threads (id, slug, title, summary, status, first_seen, "
        "last_updated) VALUES "
        "(1, 'thread-one', 'Thread One', 'sum', 'ongoing', '2026-01-01', "
        "'2026-01-01')"
    )
    conn.execute(
        "CREATE TABLE post_threads (post_id INTEGER, thread_id INTEGER)"
    )
    conn.execute(
        "INSERT INTO post_threads (post_id, thread_id) VALUES (1, 1)"
    )
    conn.execute(
        "CREATE TABLE pins (item_id INTEGER PRIMARY KEY, note TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY, run_date TEXT, status TEXT, "
        "posts_created INTEGER, detail TEXT, started_at TEXT, finished_at TEXT)"
    )
    conn.execute(
        "INSERT INTO runs (id, run_date, status, posts_created, detail, "
        "started_at, finished_at) VALUES "
        "(1, '2026-01-01', 'done', 1, 'ok', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY, name TEXT, status TEXT, "
        "phase_index INTEGER, phase_total INTEGER, phase_label TEXT, "
        "progress_current INTEGER, progress_total INTEGER, progress_label TEXT, "
        "log TEXT, error TEXT, started_at TEXT, finished_at TEXT)"
    )
    conn.execute(
        "INSERT INTO jobs (id, name, status, phase_index, phase_total, "
        "phase_label, progress_current, progress_total, progress_label, log, "
        "error, started_at, finished_at) VALUES "
        "(1, 'migrate', 'done', 1, 1, 'copy', 1, 1, 'copying', '', NULL, "
        "'2026-01-01', '2026-01-01')"
    )
    conn.commit()
    conn.close()
    return path


def test_migrate_copies_rows_and_verifies_counts(tmp_path):
    source = _make_source_db(tmp_path)
    counts = main(source)
    assert counts["items"] == 1
    assert counts["posts"] == 2
    assert counts["threads"] == 1
    assert counts["post_threads"] == 1
    assert counts["runs"] == 1
    assert counts["jobs"] == 1
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM items WHERE id = 1").fetchone()
        assert row["title"] == "Title"
        post_row = conn.execute("SELECT * FROM posts WHERE id = 1").fetchone()
        assert post_row["title"] == "Post One"
        assert post_row["item_ids"] == [1]
        assert post_row["slides_json"] == {"a": 1}

        max_thread_id = conn.execute(
            "SELECT MAX(id) AS n FROM threads"
        ).fetchone()["n"]
        new_id = conn.execute(
            "INSERT INTO threads (slug, title) VALUES ('new', 'New') "
            "RETURNING id"
        ).fetchone()["id"]
        assert new_id > max_thread_id


def test_migrate_refuses_nonempty_destination_without_force(tmp_path):
    source = _make_source_db(tmp_path)
    main(source)
    with pytest.raises(RuntimeError, match="non-empty"):
        main(source)
