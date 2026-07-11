"""Data-access helpers for `threads` + `post_threads` (content memory).

A thread is an ongoing storyline (e.g. "gpt-5-launch"). Posts attach to threads
so the pipeline can detect follow-ups and build on prior coverage.
"""

from __future__ import annotations

from typing import Any

import psycopg


def open_threads(conn: psycopg.Connection, profile_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM threads WHERE status = 'ongoing' AND profile_id = %s "
        "ORDER BY last_updated DESC",
        (profile_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_thread_by_slug(conn: psycopg.Connection, slug: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM threads WHERE slug = %s", (slug,)).fetchone()
    return dict(row) if row else None


def upsert_thread(
    conn: psycopg.Connection, *, slug: str, title: str, summary: str | None,
    profile_id: int,
) -> int:
    """Create or refresh a thread by (profile_id, slug); returns its id.

    Bumps last_updated. Scoped per-profile so two profiles independently
    opening a thread with the same derived slug don't collide.
    """
    row = conn.execute(
        "INSERT INTO threads (slug, title, summary, profile_id) "
        "VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (profile_id, slug) DO UPDATE SET "
        "title = EXCLUDED.title, summary = EXCLUDED.summary, "
        "status = 'ongoing', last_updated = now() "
        "RETURNING id",
        (slug, title, summary, profile_id),
    ).fetchone()
    return int(row["id"])


def link_post_thread(conn: psycopg.Connection, post_id: int, thread_id: int) -> None:
    conn.execute(
        "INSERT INTO post_threads (post_id, thread_id) VALUES (%s, %s) "
        "ON CONFLICT DO NOTHING",
        (post_id, thread_id),
    )


def posts_for_thread(conn: psycopg.Connection, thread_id: int) -> list[dict[str, Any]]:
    """Posts attached to a thread, newest first (id, title, status, created_at)."""
    rows = conn.execute(
        "SELECT p.id, p.title, p.status, p.created_at FROM posts p "
        "JOIN post_threads pt ON pt.post_id = p.id "
        "WHERE pt.thread_id = %s ORDER BY p.created_at DESC, p.id DESC",
        (thread_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def threads_with_posts(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """All threads (newest activity first), each with its linked posts attached."""
    rows = conn.execute("SELECT * FROM threads ORDER BY last_updated DESC").fetchall()
    out = []
    for r in rows:
        th = dict(r)
        th["posts"] = posts_for_thread(conn, th["id"])
        out.append(th)
    return out
