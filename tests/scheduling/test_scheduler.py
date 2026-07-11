from __future__ import annotations

from datetime import datetime, timedelta, timezone

from claudeshorts.scheduling import scheduler, store as sched_store


def test_seed_default_schedules_creates_three():
    scheduler.seed_default_schedules()
    from claudeshorts.store import db
    with db.connect() as conn:
        rows = conn.execute("SELECT name FROM schedules").fetchall()
    names = {r["name"] for r in rows}
    assert {"daily-full-run", "hourly-scheduled-drain", "weekly-report"} <= names


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
