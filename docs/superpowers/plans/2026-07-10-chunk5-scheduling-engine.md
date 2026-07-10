# Chunk 5: Scheduling Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-contained recurring scheduler (new `schedules` table + polling loop) so claudeshorts no longer depends on external cron/launchd — a daily full pipeline run, an hourly scheduled-posts drain, and a weekly internal performance report all self-trigger.

**Architecture:** New `claudeshorts/scheduling/` package (`store.py`, `compute.py`, `scheduler.py`) parallels chunk 2's `jobs/` package. `compute.next_run_at` is a pure function (no DB, no wall clock) so schedule math is fully unit-testable. The scheduler enqueues through chunk 2's `jobs.queue.enqueue` — it never runs a job itself, only decides when to enqueue one.

**Tech Stack:** Python 3.11+, psycopg3 (existing), no new dependencies (deliberately no cron-parsing library).

## Global Constraints

- Python 3.11+, type hints everywhere, PEP 8.
- No comments explaining *what*, only non-obvious *why*.
- No cron-expression syntax — only `daily_at` (HH:MM, optionally day-of-week-gated for weekly) and `every_minutes`.
- Full spec: `docs/superpowers/specs/2026-07-10-chunk5-scheduling-engine-design.md`.

---

## File Structure

- Modify: `claudeshorts/store/db.py` — add `schedules` table to `SCHEMA`.
- Modify: `config/settings.yaml` — new `schedule:` section.
- Create: `claudeshorts/scheduling/__init__.py`, `store.py`, `compute.py`, `scheduler.py`
- Modify: `claudeshorts/services/pipeline_service.py` — add `drain_scheduled_posts_service`
- Modify: `claudeshorts/jobs/registry.py` — add `drain_scheduled_posts` and `weekly_report` job types
- Create: `claudeshorts/services/reporting_service.py`
- Modify: `claudeshorts/dashboard/app.py` — start the scheduler thread alongside the worker thread
- Create: `tests/scheduling/test_compute.py`, `test_store.py`, `test_scheduler.py`, `tests/services/test_reporting_service.py`

---

### Task 1: `schedules` table + config section

**Files:**
- Modify: `claudeshorts/store/db.py`
- Modify: `config/settings.yaml`
- Test: `tests/store/test_db.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# tests/store/test_db.py (add)
def test_schedules_table_exists():
    with db.connect() as conn:
        row = conn.execute(
            "INSERT INTO schedules (name, job_type, kind, daily_at) "
            "VALUES ('t', 'full_run', 'daily_at', '08:00') RETURNING *"
        ).fetchone()
        assert row["enabled"] is True
        assert row["every_minutes"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_db.py::test_schedules_table_exists -v`
Expected: FAIL — `relation "schedules" does not exist`

- [ ] **Step 3: Add the table to `SCHEMA` in `claudeshorts/store/db.py`**

Add before the closing `"""` of `SCHEMA`:

```python
CREATE TABLE IF NOT EXISTS schedules (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT        NOT NULL UNIQUE,
    job_type        TEXT        NOT NULL,
    payload         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    kind            TEXT        NOT NULL,
    daily_at        TEXT,
    every_minutes   INTEGER,
    weekday         INTEGER,
    enabled         BOOLEAN     NOT NULL DEFAULT true,
    next_run_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_run_job_id BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

(`weekday` added beyond the spec's literal table — `0`-`6` Monday-Sunday,
`NULL` meaning "every day"; needed so `compute.next_run_at` can implement
the spec's "weekly modeled as `daily_at` + day-of-week check" without a
side table.)

- [ ] **Step 4: Add the config section**

Append to `config/settings.yaml`:
```yaml
schedule:
  daily_run_time: "08:00"       # HH:MM local time for the self-triggered daily run
  drain_every_minutes: 60       # how often the scheduled-posts queue is drained
  weekly_report_weekday: 0      # 0=Monday
  weekly_report_time: "09:00"
  poll_interval_seconds: 30     # scheduler poll cadence (coarser than the job worker's)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/store/test_db.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/store/db.py config/settings.yaml tests/store/test_db.py
git commit -m "feat: add schedules table and schedule config section"
```

---

### Task 2: `compute.next_run_at` (pure function)

**Files:**
- Create: `claudeshorts/scheduling/__init__.py`
- Create: `claudeshorts/scheduling/compute.py`
- Test: `tests/scheduling/test_compute.py`

**Interfaces:**
- Produces: `next_run_at(kind: str, *, daily_at: str | None = None, every_minutes: int | None = None, weekday: int | None = None, after: datetime) -> datetime`

- [ ] **Step 1: Write the failing tests**

```python
# tests/scheduling/test_compute.py
from __future__ import annotations

from datetime import datetime, timezone

from claudeshorts.scheduling.compute import next_run_at


def test_daily_at_same_day_if_time_not_passed():
    after = datetime(2026, 7, 10, 6, 0, tzinfo=timezone.utc)
    got = next_run_at("daily_at", daily_at="08:00", after=after)
    assert got == datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc)


def test_daily_at_next_day_if_time_passed():
    after = datetime(2026, 7, 10, 9, 0, tzinfo=timezone.utc)
    got = next_run_at("daily_at", daily_at="08:00", after=after)
    assert got == datetime(2026, 7, 11, 8, 0, tzinfo=timezone.utc)


def test_every_minutes_adds_interval():
    after = datetime(2026, 7, 10, 6, 0, tzinfo=timezone.utc)
    got = next_run_at("every_minutes", every_minutes=60, after=after)
    assert got == datetime(2026, 7, 10, 7, 0, tzinfo=timezone.utc)


def test_daily_at_with_weekday_skips_to_target_weekday():
    # 2026-07-10 is a Friday (weekday=4); target weekday=0 (Monday)
    after = datetime(2026, 7, 10, 6, 0, tzinfo=timezone.utc)
    got = next_run_at("daily_at", daily_at="09:00", weekday=0, after=after)
    assert got == datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)


def test_daily_at_with_weekday_same_day_if_not_passed():
    # 2026-07-13 is a Monday
    after = datetime(2026, 7, 13, 6, 0, tzinfo=timezone.utc)
    got = next_run_at("daily_at", daily_at="09:00", weekday=0, after=after)
    assert got == datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scheduling/test_compute.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.scheduling'`

- [ ] **Step 3: Implement `compute.py`**

```python
# claudeshorts/scheduling/__init__.py
```

```python
# claudeshorts/scheduling/compute.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scheduling/test_compute.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/scheduling/__init__.py claudeshorts/scheduling/compute.py tests/scheduling/test_compute.py
git commit -m "feat: add pure next_run_at schedule computation"
```

---

### Task 3: `scheduling/store.py`

**Files:**
- Create: `claudeshorts/scheduling/store.py`
- Test: `tests/scheduling/test_store.py`

**Interfaces:**
- Consumes: `claudeshorts.store.db.connect()`
- Produces: `list_due(now: datetime) -> list[dict]`, `upsert_schedule(name, job_type, payload, kind, *, daily_at=None, every_minutes=None, weekday=None) -> int`, `mark_ran(schedule_id, job_id, next_run_at) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/scheduling/test_store.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from claudeshorts.scheduling import store as sched_store


def test_upsert_schedule_is_idempotent_by_name():
    id1 = sched_store.upsert_schedule(
        "daily-full-run", "full_run", {}, "daily_at", daily_at="08:00",
    )
    id2 = sched_store.upsert_schedule(
        "daily-full-run", "full_run", {}, "daily_at", daily_at="09:00",
    )
    assert id1 == id2


def test_list_due_only_returns_due_enabled_schedules():
    sched_store.upsert_schedule("s1", "ingest", {}, "every_minutes", every_minutes=60)
    now = datetime.now(timezone.utc)
    due = sched_store.list_due(now + timedelta(hours=2))
    assert any(s["name"] == "s1" for s in due)
    due_now = sched_store.list_due(now - timedelta(hours=2))
    assert not any(s["name"] == "s1" for s in due_now)


def test_mark_ran_advances_next_run_at_and_records_job():
    sid = sched_store.upsert_schedule("s2", "ingest", {}, "every_minutes", every_minutes=30)
    new_next = datetime.now(timezone.utc) + timedelta(minutes=30)
    sched_store.mark_ran(sid, job_id=99, next_run_at=new_next)
    from claudeshorts.store import db
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM schedules WHERE id = %s", (sid,)).fetchone()
    assert row["last_run_job_id"] == 99
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scheduling/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.scheduling.store'`

- [ ] **Step 3: Implement `store.py`**

```python
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
    weekday: int | None = None,
) -> int:
    with db.connect() as conn:
        row = conn.execute(
            "INSERT INTO schedules (name, job_type, payload, kind, daily_at, "
            "every_minutes, weekday) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (name) DO UPDATE SET "
            "job_type = EXCLUDED.job_type, payload = EXCLUDED.payload, "
            "kind = EXCLUDED.kind, daily_at = EXCLUDED.daily_at, "
            "every_minutes = EXCLUDED.every_minutes, weekday = EXCLUDED.weekday "
            "RETURNING id",
            (name, job_type, Jsonb(payload), kind, daily_at, every_minutes, weekday),
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scheduling/test_store.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/scheduling/store.py tests/scheduling/test_store.py
git commit -m "feat: add scheduling/store.py data access for schedules table"
```

---

### Task 4: `drain_scheduled_posts_service` + `weekly_report` job types

**Files:**
- Modify: `claudeshorts/services/pipeline_service.py`
- Create: `claudeshorts/services/reporting_service.py`
- Modify: `claudeshorts/jobs/registry.py`
- Test: `tests/services/test_pipeline_service.py` (extend), `tests/services/test_reporting_service.py`

**Interfaces:**
- Produces: `pipeline_service.drain_scheduled_posts_service() -> list[int]`, `reporting_service.weekly_report(as_of: date | None = None) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_pipeline_service.py (add)
def test_drain_scheduled_posts_service_delegates():
    with patch("claudeshorts.services.pipeline_service.publish_due_posts") as mock_fn:
        mock_fn.return_value = [1, 2]
        result = pipeline_service.drain_scheduled_posts_service()
    mock_fn.assert_called_once_with()
    assert result == [1, 2]
```

```python
# tests/services/test_reporting_service.py
from __future__ import annotations

from datetime import date

from claudeshorts.services import reporting_service
from claudeshorts.store import connect, posts


def _mk(status="draft", **overrides):
    kwargs = dict(item_ids=[1], title="T", slides={}, captions={}, status=status)
    kwargs.update(overrides)
    with connect() as conn:
        return posts.insert_post(conn, **kwargs)


def test_weekly_report_counts_posts_by_status():
    _mk(status="draft")
    _mk(status="approved")
    _mk(status="rejected")
    report = reporting_service.weekly_report(as_of=date(2026, 7, 10))
    assert report["posts_generated"] == 3
    assert report["posts_approved"] == 1
    assert report["posts_rejected"] == 1


def test_weekly_report_has_pending_engagement_placeholder():
    report = reporting_service.weekly_report(as_of=date(2026, 7, 10))
    assert report["platform_engagement"]["status"] == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_pipeline_service.py tests/services/test_reporting_service.py -v`
Expected: FAIL — `drain_scheduled_posts_service` and
`claudeshorts.services.reporting_service` don't exist

- [ ] **Step 3: Implement `drain_scheduled_posts_service`**

Add to `claudeshorts/services/pipeline_service.py`:
```python
from ..publish import publish_due_posts

def drain_scheduled_posts_service() -> list[int]:
    return publish_due_posts()
```

- [ ] **Step 4: Implement `reporting_service.py`**

```python
"""Internal pipeline performance reporting. Real cross-platform engagement
(views/likes/follows) is out of scope until chunk 11 wires up Playwright-
based analytics scraping via logged-in browser profiles — the
`platform_engagement` field is a placeholder so the report's shape doesn't
need to change once that data exists.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..store import connect
from ..store.posts import recent_posts, status_counts
from ..store.runs import recent_runs


def weekly_report(as_of: date | None = None) -> dict[str, Any]:
    as_of = as_of or date.today()
    week_start = as_of - timedelta(days=as_of.weekday())
    week_end = week_start + timedelta(days=6)

    with connect() as conn:
        posts_this_week = recent_posts(conn, days=7)
        counts = status_counts(conn)
        runs = recent_runs(conn, limit=10)

    by_status: dict[str, int] = {}
    exports_by_platform: dict[str, int] = {}
    for p in posts_this_week:
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1

    ok_runs = sum(1 for r in runs if r["status"] == "ok")
    error_runs = sum(1 for r in runs if r["status"] == "error")

    return {
        "week_start": week_start.isoformat(), "week_end": week_end.isoformat(),
        "posts_generated": len(posts_this_week),
        "posts_approved": by_status.get("approved", 0) + by_status.get("exported", 0),
        "posts_rejected": by_status.get("rejected", 0),
        "posts_exported": by_status.get("exported", 0),
        "exports_by_platform": exports_by_platform,
        "ingest_runs": {"ok": ok_runs, "error": error_runs},
        "platform_engagement": {
            "status": "pending",
            "note": (
                "Requires Playwright-based analytics scraping via logged-in "
                "browser profiles — see chunk 11."
            ),
        },
    }
```

Note: `exports_by_platform` is left empty in this chunk — populating it
requires per-platform export tracking that doesn't exist in the `posts`
table today (only a single `status` field, not per-platform state). Flag
this as a known gap rather than fabricating data; a future chunk that adds
per-platform publish tracking (likely alongside chunk 10's real publishing
plugins) is the natural place to fill it in.

- [ ] **Step 5: Add the two new job types to `jobs/registry.py`**

```python
from ..services import reporting_service  # add to imports

JOB_HANDLERS["drain_scheduled_posts"] = lambda payload: pipeline_service.drain_scheduled_posts_service()
JOB_HANDLERS["weekly_report"] = lambda payload: reporting_service.weekly_report()
```

(Add these two lines after the existing `JOB_HANDLERS` dict literal rather
than folding them into the dict literal, to keep the diff against chunk
3's version minimal and obviously additive.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/services/test_pipeline_service.py tests/services/test_reporting_service.py tests/jobs/test_registry.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add claudeshorts/services/pipeline_service.py claudeshorts/services/reporting_service.py claudeshorts/jobs/registry.py tests/services/test_pipeline_service.py tests/services/test_reporting_service.py
git commit -m "feat: add drain_scheduled_posts and weekly_report job types"
```

---

### Task 5: `scheduler.py` polling loop + default schedule seeding

**Files:**
- Create: `claudeshorts/scheduling/scheduler.py`
- Modify: `claudeshorts/dashboard/app.py` — start the scheduler thread
- Test: `tests/scheduling/test_scheduler.py`

**Interfaces:**
- Consumes: `scheduling.store.{list_due, mark_ran, upsert_schedule}`, `scheduling.compute.next_run_at`, `jobs.queue.enqueue`
- Produces: `seed_default_schedules() -> None`, `run_forever(*, poll_interval=None, max_iterations=None) -> None`, `tick() -> int` (enqueues all currently-due schedules, returns count enqueued — the testable unit).

- [ ] **Step 1: Write the failing tests**

```python
# tests/scheduling/test_scheduler.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from claudeshorts.scheduling import scheduler, store as sched_store


def test_seed_default_schedules_creates_three():
    scheduler.seed_default_schedules()
    from claudeshorts.store import db
    with db.connect() as conn:
        rows = conn.execute("SELECT name FROM schedules").fetchall()
    names = {r["name"] for r in rows}
    assert {"daily-full-run", "hourly-scheduled-drain", "weekly-report"} <= names


def test_tick_enqueues_due_schedule_and_advances_next_run():
    sched_store.upsert_schedule(
        "due-now", "ingest", {}, "every_minutes", every_minutes=60,
    )
    from claudeshorts.store import db
    with db.connect() as conn:
        conn.execute(
            "UPDATE schedules SET next_run_at = %s WHERE name = 'due-now'",
            (datetime.now(timezone.utc) - timedelta(minutes=1),),
        )
    enqueued = scheduler.tick()
    assert enqueued >= 1
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM schedules WHERE name = 'due-now'"
        ).fetchone()
    assert row["next_run_at"] > datetime.now(timezone.utc)
    assert row["last_run_job_id"] is not None


def test_tick_skips_not_yet_due_schedule():
    sched_store.upsert_schedule(
        "future", "ingest", {}, "every_minutes", every_minutes=60,
    )
    from claudeshorts.store import db
    with db.connect() as conn:
        conn.execute(
            "UPDATE schedules SET next_run_at = %s WHERE name = 'future'",
            (datetime.now(timezone.utc) + timedelta(hours=2),),
        )
    before = scheduler.tick()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT last_run_job_id FROM schedules WHERE name = 'future'"
        ).fetchone()
    assert row["last_run_job_id"] is None


def test_run_forever_stops_after_max_iterations():
    scheduler.run_forever(poll_interval=0.01, max_iterations=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scheduling/test_scheduler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.scheduling.scheduler'`

- [ ] **Step 3: Implement `scheduler.py`**

```python
"""Recurring-schedule polling loop. Decides *when* to enqueue a job;
`claudeshorts.jobs.worker` decides *how* to run it — this module never
runs pipeline code directly, only calls `jobs.queue.enqueue`.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from ..config import settings
from ..jobs import queue as job_queue
from . import store as sched_store
from .compute import next_run_at

log = logging.getLogger("claudeshorts.scheduling")


def seed_default_schedules() -> None:
    cfg = settings().get("schedule", {})
    sched_store.upsert_schedule(
        "daily-full-run", "full_run", {}, "daily_at",
        daily_at=cfg.get("daily_run_time", "08:00"),
    )
    sched_store.upsert_schedule(
        "hourly-scheduled-drain", "drain_scheduled_posts", {}, "every_minutes",
        every_minutes=cfg.get("drain_every_minutes", 60),
    )
    sched_store.upsert_schedule(
        "weekly-report", "weekly_report", {}, "daily_at",
        daily_at=cfg.get("weekly_report_time", "09:00"),
        weekday=cfg.get("weekly_report_weekday", 0),
    )


def tick() -> int:
    """Enqueue every currently-due schedule. Returns the count enqueued."""
    now = datetime.now(timezone.utc)
    due = sched_store.list_due(now)
    for sched in due:
        job_id = job_queue.enqueue(
            sched["job_type"], sched["payload"], name=f"scheduled: {sched['name']}",
        )
        new_next = next_run_at(
            sched["kind"], daily_at=sched.get("daily_at"),
            every_minutes=sched.get("every_minutes"), weekday=sched.get("weekday"),
            after=now,
        )
        sched_store.mark_ran(sched["id"], job_id=job_id, next_run_at=new_next)
    return len(due)


def run_forever(*, poll_interval: float | None = None, max_iterations: int | None = None) -> None:
    interval = poll_interval or settings().get("schedule", {}).get("poll_interval_seconds", 30)
    i = 0
    while max_iterations is None or i < max_iterations:
        try:
            tick()
        except Exception:
            log.exception("scheduler tick failed (DB unreachable?)")
        time.sleep(interval)
        i += 1


if __name__ == "__main__":
    seed_default_schedules()
    run_forever()
```

- [ ] **Step 4: Start the scheduler thread at dashboard startup**

In `claudeshorts/dashboard/app.py`, in the same startup hook Task 7 of
chunk 2's plan added for the job worker, add:

```python
    from ..scheduling.scheduler import run_forever as run_scheduler_forever
    from ..scheduling.scheduler import seed_default_schedules

    seed_default_schedules()
    threading.Thread(target=run_scheduler_forever, daemon=True).start()
```

(alongside the existing `threading.Thread(target=run_forever, args=("dashboard-worker",), daemon=True).start()` for the job worker — both threads start in the same startup hook.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/scheduling/test_scheduler.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Manual verification**

Run: `./start-dashboard.sh`, check startup logs show no errors, then query
the schedules table directly (`psql` via the Supabase connection string,
or a quick Python one-liner using `claudeshorts.scheduling.store.list_due`
with a far-future `now`) to confirm all three default schedules exist with
sane `next_run_at` values.

- [ ] **Step 7: Commit**

```bash
git add claudeshorts/scheduling/scheduler.py claudeshorts/dashboard/app.py tests/scheduling/test_scheduler.py
git commit -m "feat: add scheduler polling loop, seed default schedules, start at dashboard startup"
```

---

### Task 6: Update checkpoint and task tracking

**Files:**
- Modify: `CHECKPOINT_LAST.md`, `TASK_QUEUE.md`

- [ ] **Step 1: Record completion**

Update `TASK_QUEUE.md` to move chunk 5 to Done. Update `CHECKPOINT_LAST.md`
with next action: chunk 6 (structured logging overhaul).

- [ ] **Step 2: Commit**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 5 complete — self-contained recurring scheduler live"
```

---

## Self-Review Notes

**Spec coverage:** `schedules` table (Task 1) matches the spec plus the
`weekday` column needed for weekly-report modeling. Pure `next_run_at`
(Task 2) covers `daily_at`, `every_minutes`, and weekday-gated weekly.
`drain_scheduled_posts`/`weekly_report` job types (Task 4) match the spec's
new job types exactly. Scheduler loop + default seeding (Task 5) matches
the spec's three defaults. `platform_engagement` placeholder (Task 4)
matches the spec's explicit deferral to chunk 11, and chunk 11's task
description was already updated (outside this plan, during brainstorming)
to include the Playwright analytics work.

**Placeholder scan:** `exports_by_platform` is flagged as an honest gap
(no per-platform tracking exists yet) rather than filled with fabricated
data — this is a documented known-gap, not a "TBD" left for later without
explanation.

**Type consistency:** `scheduling.store` row dicts (`kind`, `daily_at`,
`every_minutes`, `weekday`, `job_type`, `payload`) are consumed identically
by `scheduler.tick()` and by `compute.next_run_at`'s keyword arguments —
verified the key names match exactly between the table schema (Task 1),
the store layer (Task 3), and the scheduler (Task 5).
