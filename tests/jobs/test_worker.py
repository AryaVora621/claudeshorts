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


def test_dispatch_one_notifies_on_weekly_report_completion():
    job_id = queue.enqueue("weekly_report", {}, name="weekly_report")
    with patch.dict(
        "claudeshorts.jobs.registry.JOB_HANDLERS",
        {"weekly_report": lambda payload: "report text"},
    ), patch("claudeshorts.jobs.worker.send_notification") as mock_notify:
        worker.dispatch_one("worker-1")
    mock_notify.assert_called_once()
    assert str(job_id) in mock_notify.call_args[0][0]


def test_dispatch_one_does_not_notify_on_ordinary_completion():
    with patch.dict(
        "claudeshorts.jobs.registry.JOB_HANDLERS",
        {"ingest": lambda payload: "42 items"},
    ), patch("claudeshorts.jobs.worker.send_notification") as mock_notify:
        queue.enqueue("ingest", {}, name="ingest")
        worker.dispatch_one("worker-1")
    mock_notify.assert_not_called()


def test_dispatch_one_notifies_on_failure():
    job_id = queue.enqueue("ingest", {}, name="ingest", max_attempts=1)

    def _boom(payload):
        raise RuntimeError("kaboom")

    with patch.dict("claudeshorts.jobs.registry.JOB_HANDLERS", {"ingest": _boom}), patch(
        "claudeshorts.jobs.worker.send_notification"
    ) as mock_notify:
        worker.dispatch_one("worker-1")
    mock_notify.assert_called_once()
    assert str(job_id) in mock_notify.call_args[0][0]
    assert "kaboom" in mock_notify.call_args[0][0]


def test_dispatch_one_logs_job_id_and_duration(caplog):
    import logging
    job_id = queue.enqueue("ingest", {}, name="ingest")
    with patch.dict("claudeshorts.jobs.registry.JOB_HANDLERS", {"ingest": lambda p: "ok"}):
        with caplog.at_level(logging.INFO, logger="claudeshorts.jobs.worker"):
            worker.dispatch_one("worker-1")
    matching = [r for r in caplog.records if r.job_id == job_id]
    assert matching
    assert "completed in" in matching[-1].message or "completed in" in matching[-1].getMessage()
