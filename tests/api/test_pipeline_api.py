from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app


def test_ingest_enqueues_job():
    client = TestClient(create_app())
    resp = client.post("/api/v1/pipeline/ingest")
    assert resp.status_code == 202
    assert isinstance(resp.json()["job_id"], int)


def test_generate_enqueues_job():
    client = TestClient(create_app())
    resp = client.post("/api/v1/pipeline/generate")
    assert resp.status_code == 202


def test_render_enqueues_job_with_post_id():
    client = TestClient(create_app())
    resp = client.post("/api/v1/pipeline/render/42")
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    from claudeshorts.store import connect, jobs as store_jobs
    with connect() as conn:
        row = store_jobs.get_job(conn, job_id)
    assert row["payload"] == {"post_id": 42}


def test_run_enqueues_full_run_job():
    client = TestClient(create_app())
    resp = client.post("/api/v1/pipeline/run")
    assert resp.status_code == 202
