"""Data-access helpers for the `pins` table (operator-flagged items).

A pin marks a raw news item the operator wants turned into a post. Selection
force-includes pinned items ahead of the auto-ranked candidates; the pin is
cleared once a post is generated from that item.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def pin_item(conn: sqlite3.Connection, item_id: int, note: str | None = None) -> None:
    conn.execute(
        "INSERT INTO pins (item_id, note) VALUES (?, ?) "
        "ON CONFLICT(item_id) DO UPDATE SET note = excluded.note",
        (item_id, note),
    )


def unpin_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM pins WHERE item_id = ?", (item_id,))


def is_pinned(conn: sqlite3.Connection, item_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM pins WHERE item_id = ?", (item_id,)
    ).fetchone() is not None


def pinned_item_ids(conn: sqlite3.Connection) -> list[int]:
    """Pinned item ids, oldest pin first (FIFO into the generation queue)."""
    rows = conn.execute(
        "SELECT item_id FROM pins ORDER BY created_at ASC, item_id ASC"
    ).fetchall()
    return [r[0] for r in rows]


def pinned_items(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Pinned items joined to their item rows, oldest pin first."""
    rows = conn.execute(
        "SELECT i.*, p.note AS pin_note, p.created_at AS pinned_at "
        "FROM pins p JOIN items i ON i.id = p.item_id "
        "ORDER BY p.created_at ASC, p.item_id ASC"
    ).fetchall()
    return [dict(r) for r in rows]
