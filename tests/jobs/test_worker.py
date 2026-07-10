from __future__ import annotations

from unittest.mock import patch

from claudeshorts.jobs import queue, worker


def test_dispatch_one_runs_registered_handler_and_completes():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    with patch.dict(
        "claudeshorts.jobs.registry.JOB_HANDLERS",
        {"ingest": lambda payload: "42 items"},
    ):
        assert worker.dispatch_one("worker-1") is True
    from claudeshorts.store import db
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "COMPLETED"


def test_dispatch_one_returns_false_when_queue_empty():
    assert worker.dispatch_one("worker-1") is False


def test_dispatch_one_fails_job_on_handler_exception():
    job_id = queue.enqueue("ingest", {}, name="ingest", max_attempts=1)

    def _boom(payload):
        raise RuntimeError("kaboom")

    with patch.dict("claudeshorts.jobs.registry.JOB_HANDLERS", {"ingest": _boom}):
        worker.dispatch_one("worker-1")
    from claudeshorts.store import db
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "FAILED"
    assert "kaboom" in row["error"]


def test_dispatch_one_skips_cancel_requested_job():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    queue.request_cancel(job_id)
    assert worker.dispatch_one("worker-1") is False


def test_run_forever_stops_after_max_iterations():
    worker.run_forever("worker-1", poll_interval=0.01, max_iterations=3)


def test_dispatch_one_cancels_claimed_job_with_cancel_flag():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    from claudeshorts.store import db
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET cancel_requested = true WHERE id = %s", (job_id,)
        )
    assert worker.dispatch_one("worker-1") is True
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "CANCELLED"
    assert row["finished_at"] is not None
