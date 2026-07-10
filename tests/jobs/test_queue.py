from __future__ import annotations

from datetime import timedelta, datetime, timezone

from claudeshorts.jobs import queue
from claudeshorts.store import db


def test_backoff_doubles_then_caps():
    assert queue.backoff(1) == timedelta(seconds=5)
    assert queue.backoff(2) == timedelta(seconds=10)
    assert queue.backoff(3) == timedelta(seconds=20)
    assert queue.backoff(10) == timedelta(seconds=300)


def test_enqueue_creates_pending_job():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "PENDING"
    assert row["job_type"] == "ingest"
    assert row["max_attempts"] == 3


def test_claim_next_locks_and_marks_running():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    claimed = queue.claim_next("worker-1")
    assert claimed["id"] == job_id
    assert claimed["status"] == "RUNNING"
    assert claimed["locked_by"] == "worker-1"
    assert queue.claim_next("worker-2") is None  # nothing else pending


def test_claim_next_ignores_future_next_attempt_at():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'RETRYING', "
            "next_attempt_at = %s WHERE id = %s",
            (datetime.now(timezone.utc) + timedelta(hours=1), job_id),
        )
    assert queue.claim_next("worker-1") is None


def test_claim_next_returns_fresh_locked_at():
    queue.enqueue("ingest", {}, name="ingest")
    claimed = queue.claim_next("worker-1")
    assert claimed["locked_at"] is not None


def test_complete_marks_completed():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    queue.claim_next("worker-1")
    queue.complete(job_id, "42 items")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "COMPLETED"
    assert row["error"] is None
    assert row["finished_at"] is not None


def test_fail_retries_until_max_attempts():
    job_id = queue.enqueue("ingest", {}, name="ingest", max_attempts=2)
    queue.claim_next("worker-1")
    queue.fail(job_id, "boom 1")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "RETRYING"
    assert row["attempts"] == 1

    queue.claim_next("worker-1")
    queue.fail(job_id, "boom 2")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "FAILED"
    assert row["attempts"] == 2
    assert row["error"] == "boom 2"


def test_cancel_pending_job_removes_it_from_claim():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    queue.request_cancel(job_id)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "CANCELLED"
    assert queue.claim_next("worker-1") is None


def test_pause_then_resume():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    queue.request_pause(job_id)
    assert queue.claim_next("worker-1") is None
    queue.resume(job_id)
    claimed = queue.claim_next("worker-1")
    assert claimed["id"] == job_id


def test_cancel_running_job_only_flags_it():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    queue.claim_next("worker-1")
    queue.request_cancel(job_id)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "RUNNING"
    assert row["cancel_requested"] is True
    assert row["finished_at"] is None


def test_cancel_completed_job_is_a_noop():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    queue.claim_next("worker-1")
    queue.complete(job_id, "done")
    with db.connect() as conn:
        before = conn.execute("SELECT status, finished_at FROM jobs WHERE id = %s", (job_id,)).fetchone()
    queue.request_cancel(job_id)
    with db.connect() as conn:
        after = conn.execute("SELECT status, finished_at FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert after["status"] == "COMPLETED"
    assert after["finished_at"] == before["finished_at"]
