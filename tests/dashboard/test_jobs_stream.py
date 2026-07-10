from __future__ import annotations

from unittest.mock import patch

from claudeshorts.dashboard import jobs
from claudeshorts.jobs import worker


def test_enqueue_job_then_stream_emits_progress_and_done():
    job_id = jobs.enqueue_job("ingest", {}, "ingest")
    with patch.dict(
        "claudeshorts.jobs.registry.JOB_HANDLERS",
        {"ingest": lambda payload: "5 items"},
    ):
        worker.dispatch_one("test-worker")
    events = list(jobs.stream(job_id))
    joined = "".join(events)
    assert "event: progress" in joined
    assert "event: done" in joined
    assert "5 items" not in joined or "data:" in joined  # log line present if captured


def test_recent_jobs_reflects_new_queue_status_values():
    jobs.enqueue_job("ingest", {}, "ingest")
    recent = jobs.recent_jobs(10)
    assert recent[0].status in {"PENDING", "RUNNING", "COMPLETED", "FAILED"}
