"""Data-access helpers for the `pins` table (operator-flagged items).

A pin marks a raw news item the operator wants turned into a post. Selection
force-includes pinned items ahead of the auto-ranked candidates; the pin is
cleared once a post is generated from that item.
"""

from __future__ import annotations

from typing import Any

import psycopg


def pin_item(conn: psycopg.Connection, item_id: int, note: str | None = None) -> None:
    conn.execute(
        "INSERT INTO pins (item_id, note) VALUES (%s, %s) "
        "ON CONFLICT (item_id) DO UPDATE SET note = EXCLUDED.note",
        (item_id, note),
    )


def unpin_item(conn: psycopg.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM pins WHERE item_id = %s", (item_id,))


def is_pinned(conn: psycopg.Connection, item_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM pins WHERE item_id = %s", (item_id,)
    ).fetchone() is not None


def pinned_item_ids(conn: psycopg.Connection) -> list[int]:
    """Pinned item ids, oldest pin first (FIFO into the generation queue)."""
    rows = conn.execute(
        "SELECT item_id FROM pins ORDER BY created_at ASC, item_id ASC"
    ).fetchall()
    return [r["item_id"] for r in rows]


def pinned_items(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Pinned items joined to their item rows, oldest pin first."""
    rows = conn.execute(
        "SELECT i.*, p.note AS pin_note, p.created_at AS pinned_at "
        "FROM pins p JOIN items i ON i.id = p.item_id "
        "ORDER BY p.created_at ASC, p.item_id ASC"
    ).fetchall()
    return [dict(r) for r in rows]
