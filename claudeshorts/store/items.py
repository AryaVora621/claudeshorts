"""Data-access helpers for the `items` table (raw ingested news)."""

from __future__ import annotations

from typing import Any

import psycopg

ITEM_FIELDS = ("source", "url", "title", "summary", "published_at", "content_hash")


def insert_item(conn: psycopg.Connection, item: dict[str, Any]) -> bool:
    """Insert an item, ignoring duplicates (by unique (profile_id, content_hash)).

    Returns True if a new row was stored, False if it was a duplicate.
    Atomic via ON CONFLICT so concurrent ingestion can't race two inserts of
    the same item into a duplicate row.
    """
    cur = conn.execute(
        "INSERT INTO items "
        "(source, url, title, summary, published_at, content_hash) "
        "VALUES (%(source)s, %(url)s, %(title)s, %(summary)s, "
        "%(published_at)s, %(content_hash)s) "
        "ON CONFLICT (COALESCE(profile_id, 0), content_hash) DO NOTHING",
        {k: item.get(k) for k in ITEM_FIELDS},
    )
    return cur.rowcount > 0


def insert_manual_item(
    conn: psycopg.Connection,
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
    row = conn.execute("SELECT id FROM items WHERE content_hash = %s", (h,)).fetchone()
    return int(row["id"]), created


def count_items(conn: psycopg.Connection) -> int:
    """Total rows currently in `items`."""
    return conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]


def get_item(conn: psycopg.Connection, item_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM items WHERE id = %s", (item_id,)).fetchone()
    return dict(row) if row else None


def latest_items(conn: psycopg.Connection, limit: int = 100) -> list[dict[str, Any]]:
    """Most recently fetched items, newest first (for the dashboard browser)."""
    rows = conn.execute(
        "SELECT * FROM items ORDER BY COALESCE(published_at, fetched_at::text) DESC, "
        "id DESC LIMIT %s",
        (int(limit),),
    ).fetchall()
    return [dict(r) for r in rows]


def get_items(conn: psycopg.Connection, ids: list[int]) -> list[dict[str, Any]]:
    """Fetch items by id, preserving the given order."""
    if not ids:
        return []
    rows = conn.execute(
        "SELECT * FROM items WHERE id = ANY(%s)", (list(ids),)
    ).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def recent_items(conn: psycopg.Connection, days: int) -> list[dict[str, Any]]:
    """Items fetched within the last `days`, newest first (for selection)."""
    rows = conn.execute(
        "SELECT * FROM items WHERE fetched_at >= now() - (%s || ' days')::interval "
        "ORDER BY COALESCE(published_at, fetched_at::text) DESC",
        (int(days),),
    ).fetchall()
    return [dict(r) for r in rows]
