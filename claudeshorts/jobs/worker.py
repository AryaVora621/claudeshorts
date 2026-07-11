"""Polling worker: claims one job at a time from the queue and runs it.

Runs as a daemon thread inside the dashboard process by default, but is a
standalone entry point (`python -m claudeshorts.jobs.worker`) so it can be
split into its own process later without a redesign — `queue.claim_next`'s
`FOR UPDATE SKIP LOCKED` already makes concurrent workers safe.
"""

from __future__ import annotations

import logging
import time

from .. import logging_setup, progress
from ..config import settings
from . import queue, registry

log = logging.getLogger("claudeshorts.jobs.worker")
# Attach the context filter directly to this logger (not just to whatever
# handler configure_logging() installs) so job_id/worker_id land on every
# record emitted here even when the worker runs standalone or under a test
# harness (e.g. caplog) that never called configure_logging().
log.addFilter(logging_setup._ContextFilter())


def dispatch_one(worker_id: str) -> bool:
    """Claim and run at most one job. Returns True if a job was claimed."""
    try:
        job = queue.claim_next(worker_id)
    except Exception:
        log.exception("claim_next failed (DB unreachable?)")
        return False
    if job is None:
        return False
    if job["cancel_requested"]:
        queue.cancel_claimed(job["id"])
        return True

    handler = registry.JOB_HANDLERS.get(job["job_type"])
    with logging_setup.bind(job_id=job["id"], worker_id=worker_id):
        if handler is None:
            queue.fail(job["id"], f"no handler registered for job_type {job['job_type']!r}")
            return True

        def _sink(kind: str, payload: dict) -> None:
            from ..store import db, jobs as store_jobs
            try:
                with db.connect() as conn:
                    if kind == "phase":
                        store_jobs.save_snapshot(conn, job["id"], {
                            "phase_index": payload["index"], "phase_total": payload["total"],
                            "phase_label": payload.get("label", ""),
                        })
                    elif kind == "step":
                        store_jobs.save_snapshot(conn, job["id"], {
                            "progress_current": payload["current"],
                            "progress_total": payload["total"],
                            "progress_label": payload.get("label", ""),
                        })
            except Exception:
                pass

        progress.set_sink(_sink)
        started = time.monotonic()
        try:
            result = handler(job["payload"])
            queue.complete(job["id"], str(result) if result is not None else None)
            log.info("job %s (%s) completed in %.1fs", job["id"], job["job_type"],
                      time.monotonic() - started)
        except Exception as exc:
            log.error("job %s (%s) failed after %.1fs: %s", job["id"], job["job_type"],
                       time.monotonic() - started, exc, exc_info=True)
            queue.fail(job["id"], str(exc))
        finally:
            progress.clear_sink()
    return True


def run_forever(
    worker_id: str, *, poll_interval: float | None = None,
    max_iterations: int | None = None,
) -> None:
    """Loop claiming and running jobs. `max_iterations` is for tests only."""
    interval = poll_interval or settings().get("jobs", {}).get("poll_interval_seconds", 1.0)
    i = 0
    while max_iterations is None or i < max_iterations:
        claimed = dispatch_one(worker_id)
        if not claimed:
            time.sleep(interval)
        i += 1


if __name__ == "__main__":
    import sys
    from .. import logging_setup
    logging_setup.configure_logging()
    run_forever(sys.argv[1] if len(sys.argv) > 1 else "worker-cli")
