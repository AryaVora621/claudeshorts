"""Maps a job's `job_type` string to the pipeline call it runs.

Kept separate from `worker.py` so the worker loop never imports pipeline
modules directly — only this module does, and only lazily (inside each
wrapper), matching the existing lazy-import convention in `dashboard/app.py`.
"""

from __future__ import annotations

from typing import Any, Callable


def _full_run(payload: dict[str, Any]) -> Any:
    from ..orchestrate import run_pipeline
    return run_pipeline(force=True)


def _ingest(payload: dict[str, Any]) -> Any:
    from ..ingest import run_ingest
    return run_ingest()


def _generate(payload: dict[str, Any]) -> Any:
    from ..generate import run_generate
    return run_generate()


def _generate_from_item(payload: dict[str, Any]) -> Any:
    from ..generate import generate_for_item
    return generate_for_item(payload["item_id"])


def _render_post_by_id(post_id: int) -> str:
    from ..render.bridge import render_post
    from ..review.queue import assemble_review
    from ..store import connect, get_post

    with connect() as conn:
        post = get_post(conn, post_id)
    if not post:
        raise ValueError(f"no post {post_id}")
    result = render_post(post)
    assemble_review(post, result)
    return f"rendered post {post_id}: {result.get('frames')} frames"


def _render_post(payload: dict[str, Any]) -> Any:
    return _render_post_by_id(payload["post_id"])


JOB_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "full_run": _full_run,
    "ingest": _ingest,
    "generate": _generate,
    "generate_from_item": _generate_from_item,
    "render_post": _render_post,
}
