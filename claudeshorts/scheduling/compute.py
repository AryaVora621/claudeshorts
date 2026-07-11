"""Pure schedule-math: given a schedule's rule and 'now', when does it run
next? No DB, no wall-clock access — `after` is always passed in, which is
what makes this trivially unit-testable and keeps the scheduler loop (which
does read the wall clock) thin.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def next_run_at(
    kind: str, *, daily_at: str | None = None, every_minutes: int | None = None,
    weekday: int | None = None, after: datetime,
) -> datetime:
    if kind == "every_minutes":
        if every_minutes is None:
            raise ValueError("every_minutes required for kind='every_minutes'")
        return after + timedelta(minutes=every_minutes)

    if kind == "daily_at":
        if daily_at is None:
            raise ValueError("daily_at required for kind='daily_at'")
        hour, minute = (int(p) for p in daily_at.split(":"))
        candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if weekday is not None:
            days_ahead = (weekday - after.weekday()) % 7
            if days_ahead == 0 and candidate <= after:
                days_ahead = 7
            candidate = candidate + timedelta(days=days_ahead)
        elif candidate <= after:
            candidate = candidate + timedelta(days=1)
        return candidate

    raise ValueError(f"unknown schedule kind {kind!r}")
