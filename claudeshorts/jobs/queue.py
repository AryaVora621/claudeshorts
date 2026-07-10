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
    attempts_cap = max_attempts or _jobs_cfg().get("max_attempts", 3)
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
        conn.execute(
            "UPDATE jobs SET status = 'RUNNING', locked_by = %s, "
            "locked_at = now() WHERE id = %s",
            (worker_id, row["id"]),
        )
        row = dict(row)
        row["status"] = "RUNNING"
        row["locked_by"] = worker_id
        return row
