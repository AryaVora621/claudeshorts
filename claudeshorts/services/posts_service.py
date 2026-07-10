"""Post lifecycle actions shared by the CLI, dashboard, and (future) REST API
and Telegram bot. Each function is the single implementation of one
user-facing action — no route handler or CLI command should re-derive this
logic (goal.md: never duplicate business logic across interfaces).
"""

from __future__ import annotations

from typing import Any

from ..publish import export_post
from ..store import connect, get_post, set_schedule, set_status


def _require_post(conn, post_id: int) -> dict[str, Any]:
    post = get_post(conn, post_id)
    if not post:
        raise ValueError(f"post {post_id} not found")
    return post


def approve_post(post_id: int) -> dict[str, Any]:
    """Approve a post. Exports immediately unless it has a future schedule."""
    with connect() as conn:
        post = _require_post(conn, post_id)
        set_status(conn, post_id, "approved")
    scheduled_for = post.get("scheduled_for")
    if not scheduled_for:
        export_post(post)
        return {"post_id": post_id, "exported": True, "scheduled_for": None}
    return {"post_id": post_id, "exported": False, "scheduled_for": scheduled_for}


def reject_post(post_id: int, note: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        _require_post(conn, post_id)
        set_status(conn, post_id, "rejected", note=note)
    return {"post_id": post_id}


def schedule_post(post_id: int, scheduled_for: str | None) -> dict[str, Any]:
    with connect() as conn:
        _require_post(conn, post_id)
        set_schedule(conn, post_id, scheduled_for)
    return {"post_id": post_id, "scheduled_for": scheduled_for}


def export_post_now(post_id: int) -> dict[str, Any]:
    """Approve (if not already) and export right now, ignoring any schedule.

    Single implementation for what were two identical code paths
    (`/posts/{id}/export` and `/posts/{id}/publish-now`).
    """
    with connect() as conn:
        post = _require_post(conn, post_id)
        set_status(conn, post_id, "approved")
    export_post(post)
    return {"post_id": post_id}
