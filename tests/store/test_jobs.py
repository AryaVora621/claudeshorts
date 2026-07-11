from __future__ import annotations

from claudeshorts.store import db, jobs


def _new_job(conn, name: str) -> int:
    """Insert a bare job row the way `queue.enqueue` would, without pulling in
    the whole queue module (these tests exercise the store layer directly)."""
    row = conn.execute(
        "INSERT INTO jobs (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()
    return int(row["id"])


def test_get_job_reads_back_inserted_row():
    with db.connect() as conn:
        job_id = _new_job(conn, "ingest")
        got = jobs.get_job(conn, job_id)
        assert got["name"] == "ingest"
        assert got["status"] == "PENDING"


def test_save_snapshot_updates_progress():
    with db.connect() as conn:
        job_id = _new_job(conn, "ingest")
        jobs.save_snapshot(conn, job_id, {
            "status": "ok", "phase_index": 2, "phase_total": 2,
            "phase_label": "done", "progress_current": 10, "progress_total": 10,
            "progress_label": "10/10", "log": "line1\nline2", "error": None,
            "finished_at": "2026-07-10T00:00:00Z",
        })
        got = jobs.get_job(conn, job_id)
        assert got["status"] == "ok"
        assert got["progress_current"] == 10


def test_recent_jobs_and_max_id():
    with db.connect() as conn:
        id1 = _new_job(conn, "a")
        id2 = _new_job(conn, "b")
        assert jobs.max_id(conn) == id2
        assert [j["id"] for j in jobs.recent_jobs(conn, limit=10)][:2] == [id2, id1]


def test_mark_running_interrupted_flags_orphaned_running_job():
    with db.connect() as conn:
        job_id = _new_job(conn, "a")
        conn.execute(
            "UPDATE jobs SET status = 'RUNNING', locked_by = %s, locked_at = now() "
            "WHERE id = %s",
            ("dead-worker", job_id),
        )
        n = jobs.mark_running_interrupted(conn)
        assert n == 1
        row = jobs.get_job(conn, job_id)
        assert row["status"] == "FAILED"
        assert row["finished_at"] is not None
        assert "orphaned" in row["error"]


def test_mark_running_interrupted_leaves_pending_and_retrying_jobs_alone():
    with db.connect() as conn:
        pending_id = _new_job(conn, "pending-job")
        retrying_id = _new_job(conn, "retrying-job")
        conn.execute(
            "UPDATE jobs SET status = 'RETRYING' WHERE id = %s", (retrying_id,)
        )
        n = jobs.mark_running_interrupted(conn)
        assert n == 0
        assert jobs.get_job(conn, pending_id)["status"] == "PENDING"
        assert jobs.get_job(conn, retrying_id)["status"] == "RETRYING"


def test_save_snapshot_partial_update_preserves_other_columns():
    with db.connect() as conn:
        job_id = _new_job(conn, "ingest")
        jobs.save_snapshot(conn, job_id, {"status": "RUNNING"})
        jobs.save_snapshot(conn, job_id, {"phase_index": 2, "phase_total": 5})
        got = jobs.get_job(conn, job_id)
    assert got["status"] == "RUNNING"
    assert got["phase_index"] == 2
