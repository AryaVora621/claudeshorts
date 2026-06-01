"""Data-access helpers for the `items` table (raw ingested news)."""

from __future__ import annotations

import sqlite3
from typing import Any

ITEM_FIELDS = ("source", "url", "title", "summary", "published_at", "content_hash")


def insert_item(conn: sqlite3.Connection, item: dict[str, Any]) -> bool:
    """Insert an item, ignoring duplicates (by unique content_hash).

    Returns True if a new row was stored, False if it was a duplicate.
    """
    cur = conn.execute(
        "INSERT OR IGNORE INTO items "
        "(source, url, title, summary, published_at, content_hash) "
        "VALUES (:source, :url, :title, :summary, :published_at, :content_hash)",
        {k: item.get(k) for k in ITEM_FIELDS},
    )
    return cur.rowcount > 0


def count_items(conn: sqlite3.Connection) -> int:
    """Total rows currently in `items`."""
    return conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]


def recent_items(conn: sqlite3.Connection, days: int) -> list[dict[str, Any]]:
    """Items fetched within the last `days`, newest first (for selection)."""
    rows = conn.execute(
        "SELECT * FROM items WHERE fetched_at >= datetime('now', ?) "
        "ORDER BY COALESCE(published_at, fetched_at) DESC",
        (f"-{int(days)} days",),
    ).fetchall()
    return [dict(r) for r in rows]
