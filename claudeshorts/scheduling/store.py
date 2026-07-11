"""Data access for the `schedules` table. Kept separate from
`claudeshorts.store` since schedules are a scheduling-engine concept, not
core pipeline state — mirrors how `claudeshorts.jobs` owns the `jobs` table
logic beyond what `store.jobs` provides.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from ..store import db


def upsert_schedule(
    name: str, job_type: str, payload: dict[str, Any], kind: str, *,
    daily_at: str | None = None, every_minutes: int | None = None,
    weekday: int | None = None, initial_next_run_at: datetime | None = None,
) -> int:
    """Insert or update a schedule by name.

    `initial_next_run_at` is used ONLY on first insert (via COALESCE against
    the column's `now()` default) — the ON CONFLICT arm deliberately never
    touches next_run_at/last_run_job_id/enabled, so a restart that re-seeds
    schedules can't clobber an already-ticking schedule's due time.
    """
    with db.connect() as conn:
        row = conn.execute(
            "INSERT INTO schedules (name, job_type, payload, kind, daily_at, "
            "every_minutes, weekday, next_run_at) VALUES (%s, %s, %s, %s, %s, "
            "%s, %s, COALESCE(%s, now())) "
            "ON CONFLICT (name) DO UPDATE SET "
            "job_type = EXCLUDED.job_type, payload = EXCLUDED.payload, "
            "kind = EXCLUDED.kind, daily_at = EXCLUDED.daily_at, "
            "every_minutes = EXCLUDED.every_minutes, weekday = EXCLUDED.weekday "
            "RETURNING id",
            (
                name, job_type, Jsonb(payload), kind, daily_at, every_minutes,
                weekday, initial_next_run_at,
            ),
        ).fetchone()
        return int(row["id"])


def list_due(now: datetime) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM schedules WHERE enabled = true AND next_run_at <= %s "
            "ORDER BY id ASC",
            (now,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_ran(schedule_id: int, *, job_id: int, next_run_at: datetime) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE schedules SET last_run_job_id = %s, next_run_at = %s "
            "WHERE id = %s",
            (job_id, next_run_at, schedule_id),
        )
