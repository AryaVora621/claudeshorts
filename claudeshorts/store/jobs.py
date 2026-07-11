"""Data-access helpers for the `jobs` table (durable mirror of dashboard jobs).

Background jobs run in memory and stream live (see ``dashboard/jobs.py``); these
helpers persist a snapshot of each so the operator can revisit a job after the
server restarts. The in-memory copy is always the source of truth while a job is
alive; the database is the fallback for history.
"""

from __future__ import annotations

from typing import Any

import psycopg

# The columns a snapshot write touches (everything except id/started_at, which
# are set on insert). Kept in one place so insert + update stay in sync.
_PROGRESS_COLS = (
    "status", "phase_index", "phase_total", "phase_label",
    "progress_current", "progress_total", "progress_label",
    "log", "error", "finished_at",
)


def save_snapshot(conn: psycopg.Connection, job_id: int, snap: dict[str, Any]) -> None:
    """Persist a partial or full state update for a job (progress, log, status)."""
    present = [c for c in _PROGRESS_COLS if c in snap]
    if not present:
        return
    cols = ", ".join(f"{c} = %s" for c in present)
    conn.execute(
        f"UPDATE jobs SET {cols} WHERE id = %s",
        tuple(snap[c] for c in present) + (job_id,),
    )


def get_job(conn: psycopg.Connection, job_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    return dict(row) if row else None


def recent_jobs(conn: psycopg.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Most recent jobs, newest first (for the dashboard list)."""
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY id DESC LIMIT %s", (int(limit),)
    ).fetchall()
    return [dict(r) for r in rows]


def max_id(conn: psycopg.Connection) -> int:
    """Largest job id on record, or 0 if the table is empty."""
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM jobs").fetchone()
    return int(row["m"])


def mark_running_interrupted(conn: psycopg.Connection) -> int:
    """Flag jobs left `RUNNING` by a dead process as `FAILED`. Startup-only.

    A job only runs inside a live server process; if a row is still RUNNING
    when the table is read fresh at the next startup, its worker thread died
    with the old process (no other code path can un-RUNNING a job — claim_next
    only ever claims PENDING/RETRYING rows). FAILED is the terminal status
    here (not a bespoke "interrupted" value) because it's a real state in the
    job state machine (see claudeshorts/jobs/queue.py) that the dashboard,
    API, and CSS already know how to render; a job's own retry/backoff logic
    never re-claims a FAILED row, so this is a safe one-way exit for orphans.
    Returns the number of rows updated.
    """
    cur = conn.execute(
        "UPDATE jobs SET status = 'FAILED', finished_at = now(), "
        "error = 'orphaned: process restarted while job was RUNNING' "
        "WHERE status = 'RUNNING'"
    )
    return cur.rowcount
