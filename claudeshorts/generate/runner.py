"""Generation runner: select topics, call Claude, persist posts + thread memory."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .. import progress
from ..config import settings
from ..store import connect
from ..store.items import get_item
from ..store.pins import unpin_item
from ..store.posts import insert_post
from ..store.threads import link_post_thread, open_threads, upsert_thread
from . import style_rules
from .generator import GenerateFn, generate_post
from .select import _match_thread, select_topics

logger = logging.getLogger(__name__)

# Hard ceiling on a single batch so a typo (or runaway caller) can't kick off an
# enormous, slow run of Claude calls. Applied whenever an explicit limit is given.
MAX_BATCH = 20

# Per-item progress hook: (event, index, total, title, error). `event` is one of
# "start" | "ok" | "fail". Lets the CLI draw a live progress bar without the
# runner knowing anything about rich.
ProgressFn = Callable[[str, int, int, str, "str | None"], None]


def _prior_coverage(thread: dict) -> str:
    summary = thread.get("summary") or ""
    return f"{thread['title']}: {summary}".strip()


def _persist_post(conn, item: dict, data: dict, *, follow_up: bool) -> dict[str, Any]:
    """Insert a generated post + thread link; clear any pin on its item."""
    style_cfg = settings().get("styles", {})
    data["theme"] = style_rules.pin_brand_colors(
        data["theme"], style_cfg.get("brand_colors", {})
    )
    layout = style_rules.select_layout(
        item, style_cfg.get("layout_rules", {}), style_cfg.get("default_layout", "slideshow"),
    )
    post_id = insert_post(
        conn,
        item_ids=[item["id"]],
        title=data["title"],
        slides=data["slides"],
        captions=data["captions"],
        theme=data["theme"],
        status="draft",
        layout=layout,
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
    on_progress: ProgressFn | None = None,
) -> list[dict[str, Any]]:
    """Generate draft posts for the day's selected topics (batch of up to 20).

    Resilient: each post is generated independently, so one bad item (invalid
    model output, timeout) is logged and skipped rather than aborting the whole
    batch. `generate_fn` is injectable for tests; `on_progress` receives per-item
    events for a live CLI progress bar. Returns one summary per CREATED post;
    failures are logged (and surfaced via `on_progress`).
    """
    if limit is not None:
        limit = max(1, min(MAX_BATCH, limit))
    topics = select_topics(limit=limit)
    total = len(topics)
    results: list[dict[str, Any]] = []
    failures = 0

    with connect() as conn:
        for idx, topic in enumerate(topics, 1):
            item = topic["item"]
            thread = topic["follow_up_thread"]
            prior = _prior_coverage(thread) if thread else None
            title = item.get("title", "")

            logger.info("generating [%d/%d]: %s", idx, total, title)
            progress.step(idx, total, title)
            if on_progress:
                on_progress("start", idx, total, title, None)
            try:
                data = generate_fn(item, prior)
                result = _persist_post(conn, item, data,
                                       follow_up=thread is not None)
            except Exception as exc:  # isolate: keep the batch going
                failures += 1
                logger.warning("generation failed [%d/%d] for item %s (%s): %s",
                               idx, total, item.get("id"), title, exc)
                if on_progress:
                    on_progress("fail", idx, total, title, str(exc))
                continue
            results.append(result)
            logger.info("created post #%s [%d/%d]: %s",
                        result["post_id"], idx, total, result["title"])
            if on_progress:
                on_progress("ok", idx, total, result["title"], None)

    if failures:
        logger.info("batch complete: %d created, %d failed", len(results), failures)
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
