"""Data-access helpers for `threads` + `post_threads` (content memory).

A thread is an ongoing storyline (e.g. "gpt-5-launch"). Posts attach to threads
so the pipeline can detect follow-ups and build on prior coverage.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def open_threads(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM threads WHERE status = 'ongoing' ORDER BY last_updated DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_thread_by_slug(conn: sqlite3.Connection, slug: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM threads WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def upsert_thread(
    conn: sqlite3.Connection, *, slug: str, title: str, summary: str | None,
) -> int:
    """Create or refresh a thread by slug; returns its id. Bumps last_updated."""
    existing = get_thread_by_slug(conn, slug)
    if existing:
        conn.execute(
            "UPDATE threads SET title = ?, summary = ?, status = 'ongoing', "
            "last_updated = datetime('now') WHERE slug = ?",
            (title, summary, slug),
        )
        return int(existing["id"])
    cur = conn.execute(
        "INSERT INTO threads (slug, title, summary) VALUES (?, ?, ?)",
        (slug, title, summary),
    )
    return int(cur.lastrowid)


def link_post_thread(conn: sqlite3.Connection, post_id: int, thread_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO post_threads (post_id, thread_id) VALUES (?, ?)",
        (post_id, thread_id),
    )


def posts_for_thread(conn: sqlite3.Connection, thread_id: int) -> list[dict[str, Any]]:
    """Posts attached to a thread, newest first (id, title, status, created_at)."""
    rows = conn.execute(
        "SELECT p.id, p.title, p.status, p.created_at FROM posts p "
        "JOIN post_threads pt ON pt.post_id = p.id "
        "WHERE pt.thread_id = ? ORDER BY p.created_at DESC, p.id DESC",
        (thread_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def threads_with_posts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """All threads (newest activity first), each with its linked posts attached."""
    rows = conn.execute("SELECT * FROM threads ORDER BY last_updated DESC").fetchall()
    out = []
    for r in rows:
        th = dict(r)
        th["posts"] = posts_for_thread(conn, th["id"])
        out.append(th)
    return out
