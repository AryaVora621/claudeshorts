from __future__ import annotations

from claudeshorts.store import db


def test_connect_returns_working_connection():
    with db.connect() as conn:
        row = conn.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()  # must not raise


def test_jobs_table_has_queue_columns():
    with db.connect() as conn:
        row = conn.execute(
            "INSERT INTO jobs (name, job_type, payload) "
            "VALUES ('t', 'ingest', '{}'::jsonb) RETURNING *"
        ).fetchone()
        assert row["attempts"] == 0
        assert row["max_attempts"] == 3
        assert row["cancel_requested"] is False
        assert row["pause_requested"] is False
        assert row["locked_by"] is None
