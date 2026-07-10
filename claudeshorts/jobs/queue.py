"""Durable job queue: enqueue/claim/complete/fail/cancel/pause over the
Postgres `jobs` table. This module is the state machine; `store/jobs.py`
stays a thin table wrapper.
"""

from __future__ import annotations

from datetime import timedelta

from ..config import settings


def _jobs_cfg() -> dict:
    return settings().get("jobs", {})


def backoff(attempts: int) -> timedelta:
    """Exponential backoff for the Nth failed attempt, capped."""
    cfg = _jobs_cfg()
    base = cfg.get("base_delay_seconds", 5)
    cap = cfg.get("max_delay_seconds", 300)
    seconds = min(base * (2 ** (attempts - 1)), cap)
    return timedelta(seconds=seconds)
