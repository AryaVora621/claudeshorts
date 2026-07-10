"""Wraps the ingest/generate/render/orchestrate pipeline entry points so the
CLI, dashboard, and job registry share one call site each — no domain logic
lives here, only the coordination (e.g. render + assemble the review bundle
as one step, since every caller wants both).
"""

from __future__ import annotations

from typing import Any, Callable

from ..generate import generate_for_item, run_generate
from ..ingest import run_ingest
from ..orchestrate import run_pipeline
from ..render import render_post
from ..review import assemble_review
from ..store import connect, get_post


def run_ingest_service(since: str | None = None, limit: int | None = None) -> dict[str, Any]:
    return run_ingest(since=since, limit=limit)


def run_generate_service(
    limit: int | None = None, on_progress: Callable[..., None] | None = None,
) -> list[dict[str, Any]]:
    return run_generate(limit=limit, on_progress=on_progress)


def generate_from_item_service(item_id: int) -> dict[str, Any]:
    return generate_for_item(item_id)


def render_post_service(post_id: int) -> str:
    with connect() as conn:
        post = get_post(conn, post_id)
    if not post:
        raise ValueError(f"no post {post_id}")
    result = render_post(post)
    assemble_review(post, result)
    return f"rendered post {post_id}: {result.get('frames')} frames"


def run_full_pipeline_service(
    limit: int | None = None, force: bool = False, skip_render: bool = False,
) -> dict[str, Any]:
    return run_pipeline(limit=limit, force=force, skip_render=skip_render)
