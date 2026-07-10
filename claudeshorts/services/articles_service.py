"""Article intake actions (manual add, pin/unpin, generate-from-item) shared
by the dashboard and CLI.
"""

from __future__ import annotations

from typing import Any

from ..jobs import queue as job_queue
from ..store import connect, insert_manual_item
from ..store.pins import pin_item, unpin_item


def add_manual_article(
    title: str, url: str | None = None, summary: str | None = None,
    action: str = "pin",
) -> dict[str, Any]:
    """Insert an operator-supplied article, then either pin it or enqueue
    generation, matching the dashboard's "add article" form actions."""
    with connect() as conn:
        item_id, created = insert_manual_item(
            conn, title=title, url=url, summary=summary,
        )
    if action == "generate":
        out = generate_from_item(item_id, display_title=title)
        return {"item_id": item_id, "created": created, **out}
    with connect() as conn:
        pin_item(conn, item_id)
    return {"item_id": item_id, "created": created}


def pin_article(item_id: int) -> dict[str, Any]:
    with connect() as conn:
        pin_item(conn, item_id)
    return {"item_id": item_id}


def unpin_article(item_id: int) -> dict[str, Any]:
    with connect() as conn:
        unpin_item(conn, item_id)
    return {"item_id": item_id}


def generate_from_item(item_id: int, *, display_title: str | None = None) -> dict[str, Any]:
    name = (f"generate from “{display_title[:40]}”" if display_title
            else f"generate from item {item_id}")
    job_id = job_queue.enqueue("generate_from_item", {"item_id": item_id}, name=name)
    return {"job_id": job_id}
