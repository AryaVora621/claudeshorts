"""Dashboard-facing view over the durable job queue.

Jobs run via `claudeshorts.jobs.worker` (a polling daemon thread started at
app startup, see `dashboard/app.py`). This module only enqueues and reads —
it does not run jobs itself. SSE streaming polls the DB row on an interval
instead of reading an in-memory object, since a job may now be claimed and
executed by a different thread than the one serving the HTTP request that
enqueued it.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from ..config import settings
from ..jobs import queue as job_queue
from ..store import connect
from ..store import jobs as store_jobs

_TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED", "ok", "error", "interrupted"}


@dataclass
class JobView:
    id: int
    name: str
    status: str
    done: bool
    phase: dict[str, Any]
    step: dict[str, Any]
    started_at: str
    elapsed_seconds: float
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        # /jobs.json feeds jobs.js, which expects this exact shape (mirrors
        # the old in-memory Job.to_dict()).
        return asdict(self)


def _to_view(row: dict[str, Any]) -> JobView:
    phase_total = row.get("phase_total") or 0
    step_total = row.get("progress_total") or 0
    started = row.get("started_at")
    finished = row.get("finished_at")
    started_dt = started if isinstance(started, datetime) else datetime.now(timezone.utc)
    end_dt = finished if isinstance(finished, datetime) else datetime.now(timezone.utc)
    return JobView(
        id=row["id"], name=row["name"], status=row["status"],
        done=row["status"] in _TERMINAL_STATUSES,
        phase={"index": row.get("phase_index", 0), "total": phase_total,
               "label": row.get("phase_label", ""),
               "percent": round(100 * row.get("phase_index", 0) / phase_total) if phase_total else None},
        step={"current": row.get("progress_current", 0), "total": step_total,
              "label": row.get("progress_label", ""),
              "percent": round(100 * row.get("progress_current", 0) / step_total) if step_total else None},
        started_at=started_dt.isoformat(timespec="seconds"),
        elapsed_seconds=round(max(0.0, (end_dt - started_dt).total_seconds()), 1),
        error=row.get("error"),
    )


def enqueue_job(job_type: str, payload: dict[str, Any], name: str) -> int:
    """Enqueue a job; the worker thread picks it up on its next poll."""
    return job_queue.enqueue(job_type, payload, name=name)


def get_job(job_id: int) -> JobView | None:
    with connect() as conn:
        row = store_jobs.get_job(conn, job_id)
    return _to_view(row) if row else None


def recent_jobs(limit: int = 50) -> list[JobView]:
    with connect() as conn:
        rows = store_jobs.recent_jobs(conn, limit)
    return [_to_view(r) for r in rows]


def stream(job_id: int) -> Iterator[str]:
    """Yield SSE for a job by polling the DB row until it reaches a terminal state."""
    poll = settings().get("jobs", {}).get("poll_interval_seconds", 1.0)
    last_log_len = 0
    last_sig = None
    while True:
        with connect() as conn:
            row = store_jobs.get_job(conn, job_id)
        if row is None:
            yield "event: done\ndata: missing\n\n"
            return
        view = _to_view(row)
        sig = (view.phase["index"], view.phase["total"], view.phase["label"],
               view.step["current"], view.step["total"], view.step["label"])
        if sig != last_sig:
            last_sig = sig
            payload = {"phase": view.phase, "step": view.step,
                       "status": view.status, "elapsed_seconds": view.elapsed_seconds}
            yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
        log = row.get("log") or ""
        if len(log) > last_log_len:
            new = log[last_log_len:]
            last_log_len = len(log)
            for line in new.split("\n"):
                yield "\n".join(f"data: {part}" for part in [line] or [""]) + "\n\n"
        if view.done:
            yield f"event: done\ndata: {view.status}\n\n"
            return
        time.sleep(poll)
