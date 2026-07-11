from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app
from claudeshorts.jobs import queue


def test_retry_failed_job_reenqueues():
    client = TestClient(create_app())
    queue.enqueue("generate", {"count": 1}, name="generate", max_attempts=1)
    job = queue.claim_next("w1")
    queue.fail(job["id"], error="boom")

    resp = client.post(f"/api/v1/jobs/{job['id']}/retry")
    assert resp.status_code == 200
    new_job_id = resp.json()["job_id"]
    assert new_job_id != job["id"]


def test_retry_non_failed_job_returns_409():
    client = TestClient(create_app())
    job_id = queue.enqueue("generate", {"count": 1}, name="generate")
    resp = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert resp.status_code == 409


def test_retry_missing_job_returns_404():
    client = TestClient(create_app())
    resp = client.post("/api/v1/jobs/999999/retry")
    assert resp.status_code == 404
