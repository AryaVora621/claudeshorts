"""Data-access helpers for the `runs` table (daily pipeline run log).

Backs the once-per-day idempotency guard and a record of what each run did.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def latest_run_for_date(conn: sqlite3.Connection, run_date: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM runs WHERE run_date = ? ORDER BY id DESC LIMIT 1", (run_date,)
    ).fetchone()
    return dict(row) if row else None


def start_run(conn: sqlite3.Connection, run_date: str) -> int:
    cur = conn.execute(
        "INSERT INTO runs (run_date, status) VALUES (?, 'running')", (run_date,)
    )
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection, run_id: int, *, status: str,
    posts_created: int = 0, detail: str | None = None,
) -> None:
    conn.execute(
        "UPDATE runs SET status = ?, posts_created = ?, detail = ?, "
        "finished_at = datetime('now') WHERE id = ?",
        (status, posts_created, detail, run_id),
    )
