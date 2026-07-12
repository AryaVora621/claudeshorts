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
from ..store import db
from ..store import profiles as profiles_store
from . import store as sched_store
from .compute import next_run_at

log = logging.getLogger("claudeshorts.scheduling")


def seed_default_schedules() -> None:
    """Seed one full_run/drain_scheduled_posts/weekly_report schedule per
    active profile. Schedule names are disambiguated per profile (e.g.
    "full_run:fork-ai") so re-seeding on restart stays idempotent per
    profile via upsert_schedule's ON CONFLICT (name) behavior, and each
    schedule's payload carries {"profile_id": ...} so the job it enqueues
    knows which profile's pipeline to run.
    """
    cfg = settings().get("schedule", {})
    now = datetime.now(timezone.utc)

    daily_at = cfg.get("daily_run_time", "08:00")
    every_minutes = cfg.get("drain_every_minutes", 60)
    weekly_at = cfg.get("weekly_report_time", "09:00")
    weekly_weekday = cfg.get("weekly_report_weekday", 0)

    # One connection for the whole seeding pass (list_profiles + every
    # upsert_schedule call) rather than one connection per call — seeding N
    # profiles across 3 job types used to mean up to 3N+1 separate
    # connections opened in a tight loop, which was enough to trip
    # intermittent write-then-read visibility issues against the remote
    # Supabase pooler in test runs. A single connection/transaction avoids
    # that churn and commits everything atomically on exit.
    with db.connect() as conn:
        active_profiles = profiles_store.list_profiles(conn, active_only=True)

        for profile in active_profiles:
            slug = profile["slug"]
            payload = {"profile_id": profile["id"]}

            sched_store.upsert_schedule(
                f"full_run:{slug}", "full_run", payload, "daily_at",
                daily_at=daily_at,
                initial_next_run_at=next_run_at("daily_at", daily_at=daily_at, after=now),
                conn=conn,
            )

            sched_store.upsert_schedule(
                f"drain_scheduled_posts:{slug}", "drain_scheduled_posts", payload,
                "every_minutes",
                every_minutes=every_minutes,
                initial_next_run_at=next_run_at(
                    "every_minutes", every_minutes=every_minutes, after=now,
                ),
                conn=conn,
            )

            sched_store.upsert_schedule(
                f"weekly_report:{slug}", "weekly_report", payload, "daily_at",
                daily_at=weekly_at, weekday=weekly_weekday,
                initial_next_run_at=next_run_at(
                    "daily_at", daily_at=weekly_at, weekday=weekly_weekday, after=now,
                ),
                conn=conn,
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
