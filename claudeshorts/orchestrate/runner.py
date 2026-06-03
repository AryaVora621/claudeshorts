"""The daily pipeline runner.

Ties the stages together: ingest -> generate (select + Claude) -> render ->
review queue. Idempotent per day (guarded by the `runs` table), with bounded
retries on the network-bound stages and structured logging.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Callable

from .. import progress
from ..config import settings
from ..ingest import run_ingest
from ..generate import run_generate
from ..render import render_post
from ..review import assemble_review
from ..store import connect, get_post, init_db
from ..store.runs import finish_run, latest_run_for_date, start_run

log = logging.getLogger("claudeshorts.orchestrate")


def setup_logging(level: int = logging.INFO) -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )


def _retry(fn: Callable[[], Any], *, attempts: int = 4, base: float = 2.0,
           what: str = "step") -> Any:
    """Run fn with exponential backoff on exceptions (2s, 4s, 8s ...)."""
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - retry any transient failure
            if i == attempts - 1:
                raise
            wait = base ** (i + 1)
            log.warning("%s failed (attempt %d/%d): %s — retrying in %.0fs",
                        what, i + 1, attempts, exc, wait)
            time.sleep(wait)


def run_pipeline(
    *,
    limit: int | None = None,
    force: bool = False,
    skip_render: bool = False,
    render_fn: Callable[[dict], dict] = render_post,
) -> dict[str, Any]:
    """Run one daily batch. Returns a summary dict.

    `render_fn` is injectable for testing without a browser. Set `force` to run
    again on a day that already completed; `skip_render` to stop after generation.
    """
    setup_logging()
    init_db()
    cfg = settings()
    limit = limit or cfg.get("posts_per_day", 3)
    today = date.today().isoformat()

    with connect() as conn:
        prior = latest_run_for_date(conn, today)
        if prior and prior["status"] == "ok" and not force:
            log.info("run for %s already completed (use --force to repeat)", today)
            return {"skipped": True, "reason": "already ran today", "date": today}
        run_id = start_run(conn, today)
        conn.commit()

    # A full run moves through four reported phases so the dashboard can draw a
    # coarse phase bar; each phase reports its own per-item steps for the finer
    # bar (feed M of N, post M of N, frame M of N).
    n_phases = 4
    summary: dict[str, Any] = {"date": today, "skipped": False}
    try:
        progress.phase(1, n_phases, "ingest")
        progress.reset_step("ingesting news")
        log.info("ingesting news...")
        ingest_stats = _retry(run_ingest, what="ingest")
        summary["ingest"] = {k: ingest_stats[k] for k in
                             ("stored", "duplicates", "total_items") if k in ingest_stats}

        progress.phase(2, n_phases, "generate")
        progress.reset_step("selecting topics")
        log.info("generating up to %d posts...", limit)
        results = _retry(lambda: run_generate(limit=limit), what="generate")
        summary["generated"] = [r["post_id"] for r in results]
        summary["follow_ups"] = [r["post_id"] for r in results if r["follow_up"]]

        rendered: list[int] = []
        if skip_render:
            log.info("skip-render set: %d draft posts left for separate render",
                     len(results))
        else:
            n_render = len(results)
            for i, r in enumerate(results, 1):
                pid = r["post_id"]
                # The per-item bar is owned by the renderer (frame M of N); the
                # phase label carries which post of the batch we are on.
                progress.phase(3, n_phases, f"render · post {i}/{n_render}")
                try:
                    with connect() as conn:
                        post = get_post(conn, pid)
                    result = render_fn(post)
                    assemble_review(post, result)
                    rendered.append(pid)
                    log.info("rendered + queued post %d", pid)
                except Exception as exc:  # one bad render shouldn't fail the batch
                    log.error("render failed for post %d: %s", pid, exc)
        summary["rendered"] = rendered

        # Drain the future-posts queue: export any approved post now due.
        progress.phase(4, n_phases, "publish")
        progress.reset_step("publishing due posts")
        try:
            from ..publish import publish_due_posts
            published = publish_due_posts()
            if published:
                log.info("published %d scheduled post(s): %s", len(published), published)
            summary["published"] = published
        except Exception as exc:  # scheduling is best-effort, never fail the run
            log.error("scheduled publish failed: %s", exc)

        with connect() as conn:
            finish_run(conn, run_id, status="ok",
                       posts_created=len(results), detail=str(summary))
            conn.commit()
        log.info("run complete: generated=%d rendered=%d",
                 len(results), len(rendered))
        return summary

    except Exception as exc:
        log.exception("pipeline failed")
        with connect() as conn:
            finish_run(conn, run_id, status="error", detail=str(exc))
            conn.commit()
        raise
