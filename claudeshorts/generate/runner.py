"""Generation runner: select topics, call Claude, persist posts + thread memory."""

from __future__ import annotations

from typing import Any

from ..store import connect
from ..store.posts import insert_post
from ..store.threads import link_post_thread, upsert_thread
from .generator import GenerateFn, generate_post
from .select import select_topics


def _prior_coverage(thread: dict) -> str:
    summary = thread.get("summary") or ""
    return f"{thread['title']}: {summary}".strip()


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

            post_id = insert_post(
                conn,
                item_ids=[item["id"]],
                title=data["title"],
                slides=data["slides"],
                captions=data["captions"],
                status="draft",
            )
            thread_id = upsert_thread(
                conn,
                slug=data["thread_slug"],
                title=data["thread_title"],
                summary=data["thread_summary"],
            )
            link_post_thread(conn, post_id, thread_id)
            conn.commit()

            results.append({
                "post_id": post_id,
                "title": data["title"],
                "thread_slug": data["thread_slug"],
                "follow_up": thread is not None,
            })
    return results
