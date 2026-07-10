from __future__ import annotations

from claudeshorts.store import db, jobs


def test_insert_job_and_get_job():
    with db.connect() as conn:
        jobs.insert_job(conn, job_id=1, name="ingest")
        got = jobs.get_job(conn, 1)
        assert got["name"] == "ingest"
        assert got["status"] == "running"


def test_save_snapshot_updates_progress():
    with db.connect() as conn:
        jobs.insert_job(conn, job_id=1, name="ingest")
        jobs.save_snapshot(conn, 1, {
            "status": "ok", "phase_index": 2, "phase_total": 2,
            "phase_label": "done", "progress_current": 10, "progress_total": 10,
            "progress_label": "10/10", "log": "line1\nline2", "error": None,
            "finished_at": "2026-07-10T00:00:00Z",
        })
        got = jobs.get_job(conn, 1)
        assert got["status"] == "ok"
        assert got["progress_current"] == 10


def test_recent_jobs_and_max_id():
    with db.connect() as conn:
        jobs.insert_job(conn, job_id=1, name="a")
        jobs.insert_job(conn, job_id=2, name="b")
        assert jobs.max_id(conn) == 2
        assert [j["id"] for j in jobs.recent_jobs(conn, limit=10)] == [2, 1]


def test_mark_running_interrupted():
    with db.connect() as conn:
        jobs.insert_job(conn, job_id=1, name="a")
        n = jobs.mark_running_interrupted(conn)
        assert n == 1
        assert jobs.get_job(conn, 1)["status"] == "interrupted"
