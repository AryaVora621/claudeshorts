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


def insert_manual_item(
    conn: sqlite3.Connection,
    *,
    title: str,
    url: str | None = None,
    summary: str | None = None,
    source: str = "manual",
) -> tuple[int, bool]:
    """Insert an operator-supplied article (dashboard). Idempotent by content.

    Returns ``(item_id, created)`` — for an existing duplicate the prior id is
    returned with ``created=False`` so the caller can still pin/generate it.
    """
    from ..ingest.fetchers import content_hash  # lazy: avoids import cycle

    h = content_hash(url, title)
    created = insert_item(conn, {
        "source": source, "url": url, "title": title.strip(),
        "summary": summary, "published_at": None, "content_hash": h,
    })
    row = conn.execute("SELECT id FROM items WHERE content_hash = ?", (h,)).fetchone()
    return int(row[0]), created


def count_items(conn: sqlite3.Connection) -> int:
    """Total rows currently in `items`."""
    return conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]


def get_item(conn: sqlite3.Connection, item_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def latest_items(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    """Most recently fetched items, newest first (for the dashboard browser)."""
    rows = conn.execute(
        "SELECT * FROM items ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC "
        "LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [dict(r) for r in rows]


def get_items(conn: sqlite3.Connection, ids: list[int]) -> list[dict[str, Any]]:
    """Fetch items by id, preserving the given order."""
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT * FROM items WHERE id IN ({placeholders})", list(ids)
    ).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def recent_items(conn: sqlite3.Connection, days: int) -> list[dict[str, Any]]:
    """Items fetched within the last `days`, newest first (for selection)."""
    rows = conn.execute(
        "SELECT * FROM items WHERE fetched_at >= datetime('now', ?) "
        "ORDER BY COALESCE(published_at, fetched_at) DESC",
        (f"-{int(days)} days",),
    ).fetchall()
    return [dict(r) for r in rows]
