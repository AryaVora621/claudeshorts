"""Recurring-schedule polling loop. Decides *when* to enqueue a job;
`claudeshorts.jobs.worker` decides *how* to run it — this module never
runs pipeline code directly, only calls `jobs.queue.enqueue`.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from ..config import settings
from ..jobs import queue as job_queue
from . import store as sched_store
from .compute import next_run_at

log = logging.getLogger("claudeshorts.scheduling")


def seed_default_schedules() -> None:
    cfg = settings().get("schedule", {})
    now = datetime.now(timezone.utc)

    daily_at = cfg.get("daily_run_time", "08:00")
    sched_store.upsert_schedule(
        "daily-full-run", "full_run", {}, "daily_at",
        daily_at=daily_at,
        initial_next_run_at=next_run_at("daily_at", daily_at=daily_at, after=now),
    )

    every_minutes = cfg.get("drain_every_minutes", 60)
    sched_store.upsert_schedule(
        "hourly-scheduled-drain", "drain_scheduled_posts", {}, "every_minutes",
        every_minutes=every_minutes,
        initial_next_run_at=next_run_at(
            "every_minutes", every_minutes=every_minutes, after=now,
        ),
    )

    weekly_at = cfg.get("weekly_report_time", "09:00")
    weekly_weekday = cfg.get("weekly_report_weekday", 0)
    sched_store.upsert_schedule(
        "weekly-report", "weekly_report", {}, "daily_at",
        daily_at=weekly_at, weekday=weekly_weekday,
        initial_next_run_at=next_run_at(
            "daily_at", daily_at=weekly_at, weekday=weekly_weekday, after=now,
        ),
    )


def tick() -> int:
    """Enqueue every currently-due schedule. Returns the count of schedules
    successfully enqueued *and* marked ran. A schedule whose enqueue or
    mark_ran call fails is logged and skipped (not counted) rather than
    aborting the whole tick — otherwise one bad schedule blocks the rest.
    """
    now = datetime.now(timezone.utc)
    due = sched_store.list_due(now)
    processed = 0
    for sched in due:
        try:
            job_id = job_queue.enqueue(
                sched["job_type"], sched["payload"], name=f"scheduled: {sched['name']}",
            )
            new_next = next_run_at(
                sched["kind"], daily_at=sched.get("daily_at"),
                every_minutes=sched.get("every_minutes"), weekday=sched.get("weekday"),
                after=now,
            )
            sched_store.mark_ran(sched["id"], job_id=job_id, next_run_at=new_next)
        except Exception:
            log.exception("schedule %s failed to process (tick)", sched.get("name"))
            continue
        processed += 1
    return processed


def run_forever(*, poll_interval: float | None = None, max_iterations: int | None = None) -> None:
    interval = poll_interval if poll_interval is not None else settings().get("schedule", {}).get("poll_interval_seconds", 30)
    i = 0
    while max_iterations is None or i < max_iterations:
        try:
            tick()
        except Exception:
            log.exception("scheduler tick failed (DB unreachable?)")
        time.sleep(interval)
        i += 1


if __name__ == "__main__":
    from .. import logging_setup
    logging_setup.configure_logging()
    seed_default_schedules()
    run_forever()
