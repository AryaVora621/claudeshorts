from __future__ import annotations

from claudeshorts.store import db


def test_connect_returns_working_connection():
    with db.connect() as conn:
        row = conn.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()  # must not raise
