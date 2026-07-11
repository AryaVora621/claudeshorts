"""Data-access helpers for the `runs` table (daily pipeline run log).

Backs the once-per-day idempotency guard and a record of what each run did.
"""

from __future__ import annotations

from typing import Any

import psycopg


def latest_run_for_date(
    conn: psycopg.Connection, run_date: str, profile_id: int
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM runs WHERE run_date = %s AND profile_id = %s "
        "ORDER BY id DESC LIMIT 1",
        (run_date, profile_id),
    ).fetchone()
    return dict(row) if row else None


def recent_runs(conn: psycopg.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Most recent pipeline runs, newest first (for the dashboard history)."""
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY id DESC LIMIT %s", (int(limit),)
    ).fetchall()
    return [dict(r) for r in rows]


def start_run(conn: psycopg.Connection, run_date: str, profile_id: int) -> int:
    row = conn.execute(
        "INSERT INTO runs (run_date, status, profile_id) VALUES (%s, 'running', %s) "
        "RETURNING id",
        (run_date, profile_id),
    ).fetchone()
    return int(row["id"])


def finish_run(
    conn: psycopg.Connection, run_id: int, *, status: str,
    posts_created: int = 0, detail: str | None = None,
) -> None:
    conn.execute(
        "UPDATE runs SET status = %s, posts_created = %s, detail = %s, "
        "finished_at = now() WHERE id = %s",
        (status, posts_created, detail, run_id),
    )
