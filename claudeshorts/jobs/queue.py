"""Durable job queue: enqueue/claim/complete/fail/cancel/pause over the
Postgres `jobs` table. This module is the state machine; `store/jobs.py`
stays a thin table wrapper.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from psycopg.types.json import Jsonb

from ..config import settings
from ..store import db


def _jobs_cfg() -> dict:
    return settings().get("jobs", {})


def backoff(attempts: int) -> timedelta:
    """Exponential backoff for the Nth failed attempt, capped."""
    cfg = _jobs_cfg()
    base = cfg.get("base_delay_seconds", 5)
    cap = cfg.get("max_delay_seconds", 300)
    seconds = min(base * (2 ** (attempts - 1)), cap)
    return timedelta(seconds=seconds)


def enqueue(
    job_type: str, payload: dict[str, Any], *, name: str,
    max_attempts: int | None = None,
) -> int:
    """Add a job to the queue in PENDING state. Returns the new job id."""
    attempts_cap = max_attempts if max_attempts is not None else _jobs_cfg().get("max_attempts", 3)
    with db.connect() as conn:
        row = conn.execute(
            "INSERT INTO jobs (name, job_type, payload, max_attempts) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (name, job_type, Jsonb(payload), attempts_cap),
        ).fetchone()
        return int(row["id"])


def claim_next(worker_id: str) -> dict[str, Any] | None:
    """Atomically claim the oldest due PENDING/RETRYING job, or None."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE status IN ('PENDING', 'RETRYING') "
            "AND next_attempt_at <= now() ORDER BY id ASC "
            "LIMIT 1 FOR UPDATE SKIP LOCKED"
        ).fetchone()
        if row is None:
            return None
        row = conn.execute(
            "UPDATE jobs SET status = 'RUNNING', locked_by = %s, "
            "locked_at = now() WHERE id = %s RETURNING *",
            (worker_id, row["id"]),
        ).fetchone()
        return dict(row)


def complete(job_id: int, result: str | None) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'COMPLETED', error = NULL, "
            "finished_at = now(), log = log || %s WHERE id = %s",
            (f"\n{result}" if result else "", job_id),
        )


def fail(job_id: int, error: str) -> None:
    with db.connect() as conn:
        row = conn.execute(
            "UPDATE jobs SET attempts = attempts + 1 WHERE id = %s "
            "RETURNING attempts, max_attempts",
            (job_id,),
        ).fetchone()
        if row["attempts"] >= row["max_attempts"]:
            conn.execute(
                "UPDATE jobs SET status = 'FAILED', error = %s, "
                "finished_at = now() WHERE id = %s",
                (error, job_id),
            )
        else:
            delay = backoff(row["attempts"])
            conn.execute(
                "UPDATE jobs SET status = 'RETRYING', error = %s, "
                "next_attempt_at = now() + %s WHERE id = %s",
                (error, delay, job_id),
            )


def request_cancel(job_id: int) -> None:
    """Cancel a PENDING/RETRYING/PAUSED job immediately; flag a RUNNING one
    so the worker discards its result on completion (see spec: queue-level
    cancel only, no mid-execution interruption). Terminal jobs are untouched."""
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = CASE WHEN status = 'RUNNING' "
            "THEN 'RUNNING' ELSE 'CANCELLED' END, "
            "cancel_requested = true, "
            "finished_at = CASE WHEN status != 'RUNNING' THEN now() "
            "ELSE finished_at END "
            "WHERE id = %s AND status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED')",
            (job_id,),
        )


def cancel_claimed(job_id: int) -> None:
    """Terminalize a job the worker just claimed but discovered was already
    flagged cancel_requested. request_cancel() deliberately never moves a
    RUNNING row to CANCELLED (a worker may be mid-execution and is expected
    to finish naturally), so it only sets the flag on RUNNING jobs and lets
    the worker act on it. Without this, a job whose cancel was requested
    while RUNNING, then failed back to RETRYING (still flagged), gets
    re-claimed and would sit RUNNING forever: claim_next only selects
    PENDING/RETRYING rows, so nothing else ever moves it to a terminal
    state. Called from worker.dispatch_one right after claiming, before the
    handler runs, so it's safe to unconditionally terminalize."""
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'CANCELLED', finished_at = now() "
            "WHERE id = %s AND status = 'RUNNING'",
            (job_id,),
        )


def request_pause(job_id: int) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'PAUSED', pause_requested = true "
            "WHERE id = %s AND status IN ('PENDING', 'RETRYING')",
            (job_id,),
        )


def resume(job_id: int) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'PENDING', pause_requested = false "
            "WHERE id = %s AND status = 'PAUSED'",
            (job_id,),
        )
