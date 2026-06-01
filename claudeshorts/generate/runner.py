"""Generation runner: select topics, call Claude, persist posts + thread memory."""

from __future__ import annotations

from typing import Any

from ..store import connect
from ..store.items import get_item
from ..store.pins import unpin_item
from ..store.posts import insert_post
from ..store.threads import link_post_thread, open_threads, upsert_thread
from .generator import GenerateFn, generate_post
from .select import _match_thread, select_topics


def _prior_coverage(thread: dict) -> str:
    summary = thread.get("summary") or ""
    return f"{thread['title']}: {summary}".strip()


def _persist_post(conn, item: dict, data: dict, *, follow_up: bool) -> dict[str, Any]:
    """Insert a generated post + thread link; clear any pin on its item."""
    post_id = insert_post(
        conn,
        item_ids=[item["id"]],
        title=data["title"],
        slides=data["slides"],
        captions=data["captions"],
        theme=data["theme"],
        status="draft",
    )
    thread_id = upsert_thread(
        conn,
        slug=data["thread_slug"],
        title=data["thread_title"],
        summary=data["thread_summary"],
    )
    link_post_thread(conn, post_id, thread_id)
    unpin_item(conn, item["id"])  # consumed — drop it from the manual queue
    conn.commit()
    return {
        "post_id": post_id,
        "title": data["title"],
        "thread_slug": data["thread_slug"],
        "follow_up": follow_up,
    }


def run_generate(
    limit: int | None = None,
    *,
    generate_fn: GenerateFn = generate_post,
) -> list[dict[str, Any]]:
    """Generate draft posts for the day's selected topics.

    `generate_fn` is injectable so the pipeline can be tested without a live
    Claude call. Returns a summary per created post.
    """
    topics = select_topics(limit=limit)
    results: list[dict[str, Any]] = []

    with connect() as conn:
        for topic in topics:
            item = topic["item"]
            thread = topic["follow_up_thread"]
            prior = _prior_coverage(thread) if thread else None

            data = generate_fn(item, prior)
            results.append(_persist_post(conn, item, data,
                                         follow_up=thread is not None))
    return results


def generate_for_item(
    item_id: int, *, generate_fn: GenerateFn = generate_post,
) -> dict[str, Any]:
    """Generate a single draft post from one specific item (dashboard action).

    Bypasses daily selection but still consults content memory so a matching
    open thread becomes a follow-up. Raises if the item id is unknown.
    """
    with connect() as conn:
        item = get_item(conn, item_id)
        if not item:
            raise ValueError(f"no item with id {item_id}")
        thread = _match_thread(item, open_threads(conn))
        prior = _prior_coverage(thread) if thread else None
        data = generate_fn(item, prior)
        return _persist_post(conn, item, data, follow_up=thread is not None)
