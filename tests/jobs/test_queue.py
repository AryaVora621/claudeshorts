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
