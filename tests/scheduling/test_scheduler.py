from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from claudeshorts.scheduling import compute, scheduler, store as sched_store


def test_seed_default_schedules_creates_three():
    scheduler.seed_default_schedules()
    from claudeshorts.store import db
    with db.connect() as conn:
        rows = conn.execute("SELECT name FROM schedules").fetchall()
    names = {r["name"] for r in rows}
    assert {"daily-full-run", "hourly-scheduled-drain", "weekly-report"} <= names


def test_seed_default_schedules_leaves_nothing_due_immediately():
    scheduler.seed_default_schedules()
    just_after_seed = datetime.now(timezone.utc) + timedelta(seconds=1)
    due = sched_store.list_due(just_after_seed)
    names = {s["name"] for s in due}
    assert not (
        {"daily-full-run", "hourly-scheduled-drain", "weekly-report"} & names
    )


def test_seed_default_schedules_next_run_at_matches_compute():
    from claudeshorts.config import settings
    cfg = settings().get("schedule", {})
    before = datetime.now(timezone.utc)
    scheduler.seed_default_schedules()
    after = datetime.now(timezone.utc)

    from claudeshorts.store import db
    with db.connect() as conn:
        rows = {
            r["name"]: r["next_run_at"]
            for r in conn.execute(
                "SELECT name, next_run_at FROM schedules"
            ).fetchall()
        }

    # daily_at kinds round to :00 seconds, so they're stable regardless of
    # exactly when `after` was sampled inside seed_default_schedules() —
    # assert those two exactly against either bound.
    daily_at = cfg.get("daily_run_time", "08:00")
    weekly_at = cfg.get("weekly_report_time", "09:00")
    weekly_weekday = cfg.get("weekly_report_weekday", 0)

    expected_daily_choices = {
        compute.next_run_at("daily_at", daily_at=daily_at, after=anchor)
        for anchor in (before, after)
    }
    expected_weekly_choices = {
        compute.next_run_at(
            "daily_at", daily_at=weekly_at, weekday=weekly_weekday, after=anchor,
        )
        for anchor in (before, after)
    }
    assert rows["daily-full-run"] in expected_daily_choices
    assert rows["weekly-report"] in expected_weekly_choices

    # every_minutes preserves sub-second precision from whatever instant
    # seed_default_schedules() sampled internally, which only has to fall
    # between `before` and `after` (plus the configured offset) — assert a
    # tolerance window instead of exact equality.
    drain_minutes = cfg.get("drain_every_minutes", 60)
    lower = before + timedelta(minutes=drain_minutes)
    upper = after + timedelta(minutes=drain_minutes)
    assert lower <= rows["hourly-scheduled-drain"] <= upper


def test_reseeding_does_not_reset_next_run_at():
    scheduler.seed_default_schedules()
    from claudeshorts.store import db
    with db.connect() as conn:
        conn.execute(
            "UPDATE schedules SET next_run_at = %s, last_run_job_id = 42, "
            "enabled = false WHERE name = 'daily-full-run'",
            (datetime.now(timezone.utc) + timedelta(days=3),),
        )
        row_before = conn.execute(
            "SELECT next_run_at, last_run_job_id, enabled FROM schedules "
            "WHERE name = 'daily-full-run'"
        ).fetchone()

    # Re-seed (simulating a process restart) must not touch next_run_at,
    # last_run_job_id, or enabled for an already-running schedule.
    scheduler.seed_default_schedules()

    with db.connect() as conn:
        row_after = conn.execute(
            "SELECT next_run_at, last_run_job_id, enabled FROM schedules "
            "WHERE name = 'daily-full-run'"
        ).fetchone()

    assert row_after["next_run_at"] == row_before["next_run_at"]
    assert row_after["last_run_job_id"] == row_before["last_run_job_id"]
    assert row_after["enabled"] == row_before["enabled"]


def test_tick_enqueues_due_schedule_and_advances_next_run():
    sched_store.upsert_schedule(
        "due-now", "ingest", {}, "every_minutes", every_minutes=60,
    )
    from claudeshorts.store import db
    with db.connect() as conn:
        conn.execute(
            "UPDATE schedules SET next_run_at = %s WHERE name = 'due-now'",
            (datetime.now(timezone.utc) - timedelta(minutes=1),),
        )
    enqueued = scheduler.tick()
    assert enqueued >= 1
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM schedules WHERE name = 'due-now'"
        ).fetchone()
    assert row["next_run_at"] > datetime.now(timezone.utc)
    assert row["last_run_job_id"] is not None


def test_tick_skips_not_yet_due_schedule():
    sched_store.upsert_schedule(
        "future", "ingest", {}, "every_minutes", every_minutes=60,
    )
    from claudeshorts.store import db
    with db.connect() as conn:
        conn.execute(
            "UPDATE schedules SET next_run_at = %s WHERE name = 'future'",
            (datetime.now(timezone.utc) + timedelta(hours=2),),
        )
    before = scheduler.tick()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT last_run_job_id FROM schedules WHERE name = 'future'"
        ).fetchone()
    assert row["last_run_job_id"] is None


def test_run_forever_stops_after_max_iterations():
    scheduler.run_forever(poll_interval=0.01, max_iterations=2)


def test_tick_contains_mark_ran_failure_and_still_processes_other_schedules(monkeypatch):
    sched_store.upsert_schedule(
        "broken", "ingest", {}, "every_minutes", every_minutes=60,
    )
    sched_store.upsert_schedule(
        "healthy", "ingest", {}, "every_minutes", every_minutes=60,
    )
    from claudeshorts.store import db
    with db.connect() as conn:
        conn.execute(
            "UPDATE schedules SET next_run_at = %s WHERE name IN ('broken', 'healthy')",
            (datetime.now(timezone.utc) - timedelta(minutes=1),),
        )

    real_mark_ran = sched_store.mark_ran
    enqueue_calls = []
    real_enqueue = scheduler.job_queue.enqueue

    def spy_enqueue(job_type, payload, *, name):
        enqueue_calls.append(name)
        return real_enqueue(job_type, payload, name=name)

    def flaky_mark_ran(schedule_id, *, job_id, next_run_at):
        with db.connect() as conn:
            row = conn.execute(
                "SELECT name FROM schedules WHERE id = %s", (schedule_id,)
            ).fetchone()
        if row["name"] == "broken":
            raise RuntimeError("simulated mark_ran failure")
        return real_mark_ran(schedule_id, job_id=job_id, next_run_at=next_run_at)

    monkeypatch.setattr(scheduler.job_queue, "enqueue", spy_enqueue)
    monkeypatch.setattr(sched_store, "mark_ran", flaky_mark_ran)

    processed = scheduler.tick()

    # Both were enqueued exactly once each (no re-enqueue within this tick),
    # but only the healthy one counts as processed and only it got a fresh
    # next_run_at / last_run_job_id.
    assert enqueue_calls.count("scheduled: broken") == 1
    assert enqueue_calls.count("scheduled: healthy") == 1
    assert processed == 1

    with db.connect() as conn:
        broken = conn.execute(
            "SELECT last_run_job_id, next_run_at FROM schedules WHERE name = 'broken'"
        ).fetchone()
        healthy = conn.execute(
            "SELECT last_run_job_id, next_run_at FROM schedules WHERE name = 'healthy'"
        ).fetchone()

    # broken's mark_ran failed, so it's untouched and still due -> it will
    # be picked up again by the *next* tick (not duplicated within this one).
    assert broken["last_run_job_id"] is None
    assert broken["next_run_at"] <= datetime.now(timezone.utc)
    assert healthy["last_run_job_id"] is not None
    assert healthy["next_run_at"] > datetime.now(timezone.utc)

    # A second tick re-enqueues only the still-due "broken" schedule, proving
    # tick() didn't silently duplicate it during the first pass.
    monkeypatch.setattr(sched_store, "mark_ran", real_mark_ran)
    processed_2 = scheduler.tick()
    assert processed_2 == 1
    assert enqueue_calls.count("scheduled: broken") == 2
    assert enqueue_calls.count("scheduled: healthy") == 1
