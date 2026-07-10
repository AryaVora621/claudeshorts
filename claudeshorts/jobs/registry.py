"""Maps a job's `job_type` string to the service function that runs it.

No pipeline logic lives here — only the lookup. Business logic is in
`claudeshorts.services`, shared with the CLI and dashboard.
"""

from __future__ import annotations

from typing import Any, Callable

from ..services import pipeline_service

JOB_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "full_run": lambda payload: pipeline_service.run_full_pipeline_service(force=True),
    "ingest": lambda payload: pipeline_service.run_ingest_service(),
    "generate": lambda payload: pipeline_service.run_generate_service(),
    "generate_from_item": lambda payload: pipeline_service.generate_from_item_service(payload["item_id"]),
    "render_post": lambda payload: pipeline_service.render_post_service(payload["post_id"]),
}
