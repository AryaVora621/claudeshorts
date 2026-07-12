"""Maps a job's `job_type` string to the service function that runs it.

No pipeline logic lives here — only the lookup. Business logic is in
`claudeshorts.services`, shared with the CLI and dashboard.
"""

from __future__ import annotations

from typing import Any, Callable

from ..services import pipeline_service, reporting_service


def _render_post_job(payload: dict[str, Any]) -> str:
    """Render, then collapse the summary dict into the readable one-liner
    the job log has always shown (the worker just ``str()``s whatever a
    handler returns — a dict would otherwise dump as a raw repr)."""
    post_id = payload["post_id"]
    summary = pipeline_service.render_post_service(post_id)
    return (
        f"rendered post {post_id}: {summary['frames']} frames, "
        f"{summary['duration_ms']}ms, audio={summary['audio_mode']}"
    )


JOB_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "full_run": lambda payload: pipeline_service.run_full_pipeline_service(
        profile_id=payload["profile_id"], force=True,
    ),
    "ingest": lambda payload: pipeline_service.run_ingest_service(profile_id=payload["profile_id"]),
    "generate": lambda payload: pipeline_service.run_generate_service(profile_id=payload["profile_id"]),
    # generate_from_item / render_post are already per-item/per-post, which
    # already carry an implicit profile via the item/post row itself now
    # that Task 4's schema is in place — left unchanged.
    "generate_from_item": lambda payload: pipeline_service.generate_from_item_service(payload["item_id"]),
    "render_post": _render_post_job,
}

JOB_HANDLERS["drain_scheduled_posts"] = lambda payload: pipeline_service.drain_scheduled_posts_service()
JOB_HANDLERS["weekly_report"] = lambda payload: reporting_service.weekly_report()
