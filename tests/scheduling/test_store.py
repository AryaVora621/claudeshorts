from __future__ import annotations

from datetime import datetime, timedelta, timezone

from claudeshorts.scheduling import store as sched_store


def test_upsert_schedule_is_idempotent_by_name():
	id1 = sched_store.upsert_schedule(
		"daily-full-run", "full_run", {}, "daily_at", daily_at="08:00",
	)
	id2 = sched_store.upsert_schedule(
		"daily-full-run", "full_run", {}, "daily_at", daily_at="09:00",
	)
	assert id1 == id2


def test_list_due_only_returns_due_enabled_schedules():
	sched_store.upsert_schedule("s1", "ingest", {}, "every_minutes", every_minutes=60)
	now = datetime.now(timezone.utc)
	due = sched_store.list_due(now + timedelta(hours=2))
	assert any(s["name"] == "s1" for s in due)
	due_now = sched_store.list_due(now - timedelta(hours=2))
	assert not any(s["name"] == "s1" for s in due_now)


def test_mark_ran_advances_next_run_at_and_records_job():
	sid = sched_store.upsert_schedule("s2", "ingest", {}, "every_minutes", every_minutes=30)
	new_next = datetime.now(timezone.utc) + timedelta(minutes=30)
	sched_store.mark_ran(sid, job_id=99, next_run_at=new_next)
	from claudeshorts.store import db
	with db.connect() as conn:
		row = conn.execute("SELECT * FROM schedules WHERE id = %s", (sid,)).fetchone()
	assert row["last_run_job_id"] == 99
