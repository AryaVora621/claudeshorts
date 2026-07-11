from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app
from claudeshorts.jobs import queue


def test_get_job_not_found():
    client = TestClient(create_app())
    resp = client.get("/api/v1/jobs/999999")
    assert resp.status_code == 404


def test_get_job_found():
    client = TestClient(create_app())
    job_id = queue.enqueue("ingest", {}, name="ingest")
    resp = client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id
    assert resp.json()["status"] == "PENDING"


def test_list_jobs():
    client = TestClient(create_app())
    queue.enqueue("ingest", {}, name="ingest")
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_cancel_job():
    client = TestClient(create_app())
    job_id = queue.enqueue("ingest", {}, name="ingest")
    resp = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "CANCELLED"


def test_pause_and_resume_job():
    client = TestClient(create_app())
    job_id = queue.enqueue("ingest", {}, name="ingest")
    client.post(f"/api/v1/jobs/{job_id}/pause")
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "PAUSED"
    client.post(f"/api/v1/jobs/{job_id}/resume")
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "PENDING"


def test_cancel_nonexistent_job_404():
    client = TestClient(create_app())
    resp = client.post("/api/v1/jobs/999999/cancel")
    assert resp.status_code == 404


def test_pause_nonexistent_job_404():
    client = TestClient(create_app())
    resp = client.post("/api/v1/jobs/999999/pause")
    assert resp.status_code == 404


def test_resume_nonexistent_job_404():
    client = TestClient(create_app())
    resp = client.post("/api/v1/jobs/999999/resume")
    assert resp.status_code == 404


def test_cancel_completed_job_409():
    client = TestClient(create_app())
    job_id = queue.enqueue("ingest", {}, name="ingest")
    queue.claim_next("worker-1")
    queue.complete(job_id, "done")
    resp = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert resp.status_code == 409
    assert "COMPLETED" in resp.json()["detail"]
