"""Data-access helpers for the `posts` table (generated content + lifecycle)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _row_to_post(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["item_ids"] = json.loads(d["item_ids"]) if d.get("item_ids") else []
    d["slides"] = json.loads(d["slides_json"]) if d.get("slides_json") else None
    d["theme"] = json.loads(d["theme_json"]) if d.get("theme_json") else None
    d["captions"] = json.loads(d["captions_json"]) if d.get("captions_json") else None
    return d


def insert_post(
    conn: sqlite3.Connection,
    *,
    item_ids: list[int],
    title: str,
    slides: Any,
    captions: Any,
    theme: Any = None,
    status: str = "draft",
) -> int:
    """Insert a generated post; returns the new post id."""
    cur = conn.execute(
        "INSERT INTO posts "
        "(item_ids, status, title, slides_json, theme_json, captions_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (json.dumps(item_ids), status, title,
         json.dumps(slides), json.dumps(theme), json.dumps(captions)),
    )
    return int(cur.lastrowid)


def get_post(conn: sqlite3.Connection, post_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    return _row_to_post(row) if row else None


def recent_posts(conn: sqlite3.Connection, days: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM posts WHERE created_at >= datetime('now', ?) "
        "ORDER BY created_at DESC",
        (f"-{int(days)} days",),
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def posts_by_status(conn: sqlite3.Connection, status: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM posts WHERE status = ? ORDER BY created_at DESC", (status,)
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def all_posts(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    """Every post, newest first (for the dashboard browser)."""
    rows = conn.execute(
        "SELECT * FROM posts ORDER BY created_at DESC, id DESC LIMIT ?", (int(limit),)
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Map of status -> count across all posts (for the overview tiles)."""
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM posts GROUP BY status"
    ).fetchall()
    return {r["status"]: r["n"] for r in rows}


def set_schedule(
    conn: sqlite3.Connection, post_id: int, scheduled_for: str | None
) -> None:
    """Set (or clear, with None) a post's target publish date (YYYY-MM-DD)."""
    conn.execute(
        "UPDATE posts SET scheduled_for = ? WHERE id = ?", (scheduled_for, post_id)
    )


def scheduled_posts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Posts with a target publish date set, soonest first."""
    rows = conn.execute(
        "SELECT * FROM posts WHERE scheduled_for IS NOT NULL "
        "ORDER BY scheduled_for ASC, id ASC"
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def due_posts(conn: sqlite3.Connection, on_date: str) -> list[dict[str, Any]]:
    """Approved posts whose scheduled_for has arrived (<= on_date)."""
    rows = conn.execute(
        "SELECT * FROM posts WHERE status = 'approved' "
        "AND scheduled_for IS NOT NULL AND scheduled_for <= ? "
        "ORDER BY scheduled_for ASC, id ASC",
        (on_date,),
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def used_item_ids(conn: sqlite3.Connection, days: int) -> set[int]:
    """item ids already consumed by recent posts (for selection dedupe)."""
    ids: set[int] = set()
    for post in recent_posts(conn, days):
        ids.update(post["item_ids"])
    return ids


def set_status(
    conn: sqlite3.Connection, post_id: int, status: str,
    *, note: str | None = None, published_at: str | None = None,
) -> None:
    conn.execute(
        "UPDATE posts SET status = ?, "
        "review_note = COALESCE(?, review_note), "
        "published_at = COALESCE(?, published_at) WHERE id = ?",
        (status, note, published_at, post_id),
    )
