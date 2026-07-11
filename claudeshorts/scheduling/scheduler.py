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
    sched_store.upsert_schedule(
        "daily-full-run", "full_run", {}, "daily_at",
        daily_at=cfg.get("daily_run_time", "08:00"),
    )
    sched_store.upsert_schedule(
        "hourly-scheduled-drain", "drain_scheduled_posts", {}, "every_minutes",
        every_minutes=cfg.get("drain_every_minutes", 60),
    )
    sched_store.upsert_schedule(
        "weekly-report", "weekly_report", {}, "daily_at",
        daily_at=cfg.get("weekly_report_time", "09:00"),
        weekday=cfg.get("weekly_report_weekday", 0),
    )


def tick() -> int:
    """Enqueue every currently-due schedule. Returns the count enqueued."""
    now = datetime.now(timezone.utc)
    due = sched_store.list_due(now)
    for sched in due:
        job_id = job_queue.enqueue(
            sched["job_type"], sched["payload"], name=f"scheduled: {sched['name']}",
        )
        new_next = next_run_at(
            sched["kind"], daily_at=sched.get("daily_at"),
            every_minutes=sched.get("every_minutes"), weekday=sched.get("weekday"),
            after=now,
        )
        sched_store.mark_ran(sched["id"], job_id=job_id, next_run_at=new_next)
    return len(due)


def run_forever(*, poll_interval: float | None = None, max_iterations: int | None = None) -> None:
    interval = poll_interval or settings().get("schedule", {}).get("poll_interval_seconds", 30)
    i = 0
    while max_iterations is None or i < max_iterations:
        try:
            tick()
        except Exception:
            log.exception("scheduler tick failed (DB unreachable?)")
        time.sleep(interval)
        i += 1


if __name__ == "__main__":
    seed_default_schedules()
    run_forever()
