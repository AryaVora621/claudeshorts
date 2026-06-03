"""Data-access helpers for the `jobs` table (durable mirror of dashboard jobs).

Background jobs run in memory and stream live (see ``dashboard/jobs.py``); these
helpers persist a snapshot of each so the operator can revisit a job after the
server restarts. The in-memory copy is always the source of truth while a job is
alive; the database is the fallback for history.
"""

from __future__ import annotations

import sqlite3
from typing import Any

# The columns a snapshot write touches (everything except id/started_at, which
# are set on insert). Kept in one place so insert + update stay in sync.
_PROGRESS_COLS = (
    "status", "phase_index", "phase_total", "phase_label",
    "progress_current", "progress_total", "progress_label",
    "log", "error", "finished_at",
)


def insert_job(conn: sqlite3.Connection, *, job_id: int, name: str) -> None:
    """Record a newly started job. ``job_id`` matches the in-memory job id."""
    conn.execute(
        "INSERT OR REPLACE INTO jobs (id, name, status) VALUES (?, ?, 'running')",
        (job_id, name),
    )
    conn.commit()


def save_snapshot(conn: sqlite3.Connection, job_id: int, snap: dict[str, Any]) -> None:
    """Persist the current state of a job (progress, log, status, finish time)."""
    cols = ", ".join(f"{c} = ?" for c in _PROGRESS_COLS)
    conn.execute(
        f"UPDATE jobs SET {cols} WHERE id = ?",
        tuple(snap.get(c) for c in _PROGRESS_COLS) + (job_id,),
    )
    conn.commit()


def get_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def recent_jobs(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Most recent jobs, newest first (for the dashboard list)."""
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (int(limit),)
    ).fetchall()
    return [dict(r) for r in rows]


def max_id(conn: sqlite3.Connection) -> int:
    """Largest job id on record, or 0 if the table is empty."""
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM jobs").fetchone()
    return int(row["m"])


def mark_running_interrupted(conn: sqlite3.Connection) -> int:
    """Flag jobs left `running` by a dead process as `interrupted`. Startup-only.

    A job only runs inside a live server process; if a row is still `running`
    when the table is read fresh, its thread died with the old process. Returns
    the number of rows updated.
    """
    cur = conn.execute(
        "UPDATE jobs SET status = 'interrupted', finished_at = datetime('now') "
        "WHERE status = 'running'"
    )
    conn.commit()
    return cur.rowcount
