"""Data-access helpers for the `posts` table (generated content + lifecycle)."""

from __future__ import annotations

from typing import Any

import psycopg


def _row_to_post(row: dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    d["item_ids"] = d.get("item_ids") or []
    d["slides"] = d.get("slides_json")
    d["theme"] = d.get("theme_json")
    d["captions"] = d.get("captions_json")
    d["layout"] = d.get("layout") or "slideshow"
    return d


def insert_post(
    conn: psycopg.Connection,
    *,
    item_ids: list[int],
    title: str,
    slides: Any,
    captions: Any,
    theme: Any = None,
    status: str = "draft",
    layout: str = "slideshow",
) -> int:
    """Insert a generated post; returns the new post id."""
    row = conn.execute(
        "INSERT INTO posts "
        "(item_ids, status, title, slides_json, theme_json, captions_json, layout) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            psycopg.types.json.Jsonb(item_ids), status, title,
            psycopg.types.json.Jsonb(slides), psycopg.types.json.Jsonb(theme),
            psycopg.types.json.Jsonb(captions), layout,
        ),
    ).fetchone()
    return int(row["id"])


def get_post(conn: psycopg.Connection, post_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM posts WHERE id = %s", (post_id,)).fetchone()
    return _row_to_post(row) if row else None


def recent_posts(conn: psycopg.Connection, days: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM posts WHERE created_at >= now() - (%s || ' days')::interval "
        "ORDER BY created_at DESC",
        (int(days),),
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def posts_by_status(conn: psycopg.Connection, status: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM posts WHERE status = %s ORDER BY created_at DESC", (status,)
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def all_posts(conn: psycopg.Connection, limit: int = 200) -> list[dict[str, Any]]:
    """Every post, newest first (for the dashboard browser)."""
    rows = conn.execute(
        "SELECT * FROM posts ORDER BY created_at DESC, id DESC LIMIT %s", (int(limit),)
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def status_counts(conn: psycopg.Connection) -> dict[str, int]:
    """Map of status -> count across all posts (for the overview tiles)."""
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM posts GROUP BY status"
    ).fetchall()
    return {r["status"]: r["n"] for r in rows}


def set_schedule(
    conn: psycopg.Connection, post_id: int, scheduled_for: str | None
) -> None:
    """Set (or clear, with None) a post's target publish date (YYYY-MM-DD)."""
    conn.execute(
        "UPDATE posts SET scheduled_for = %s WHERE id = %s", (scheduled_for, post_id)
    )


def scheduled_posts(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Posts with a target publish date set, soonest first."""
    rows = conn.execute(
        "SELECT * FROM posts WHERE scheduled_for IS NOT NULL "
        "ORDER BY scheduled_for ASC, id ASC"
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def due_posts(conn: psycopg.Connection, on_date: str) -> list[dict[str, Any]]:
    """Approved posts whose scheduled_for has arrived (<= on_date)."""
    rows = conn.execute(
        "SELECT * FROM posts WHERE status = 'approved' "
        "AND scheduled_for IS NOT NULL AND scheduled_for <= %s "
        "ORDER BY scheduled_for ASC, id ASC",
        (on_date,),
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def used_item_ids(conn: psycopg.Connection, days: int) -> set[int]:
    """item ids already consumed by recent posts (for selection dedupe)."""
    ids: set[int] = set()
    for post in recent_posts(conn, days):
        ids.update(post["item_ids"])
    return ids


def set_status(
    conn: psycopg.Connection, post_id: int, status: str,
    *, note: str | None = None, published_at: str | None = None,
) -> None:
    conn.execute(
        "UPDATE posts SET status = %s, "
        "review_note = COALESCE(%s, review_note), "
        "published_at = COALESCE(%s, published_at) WHERE id = %s",
        (status, note, published_at, post_id),
    )
