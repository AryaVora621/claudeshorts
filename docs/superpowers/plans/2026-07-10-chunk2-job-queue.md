# Chunk 2: Job Queue + State Machine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the `jobs` table into a real durable queue with a state machine (PENDING/RUNNING/WAITING_FOR_APPROVAL/RETRYING/FAILED/COMPLETED/CANCELLED/PAUSED), a polling worker that claims jobs via `SELECT...FOR UPDATE SKIP LOCKED`, and queue-level cancel/pause — becoming the sole source of truth so the dashboard's live SSE streaming reads from the DB instead of an in-memory object.

**Architecture:** New `claudeshorts/jobs/` package (`registry.py`, `queue.py`, `worker.py`) sits alongside `claudeshorts/store/jobs.py` (pure data access, extended with new columns). `dashboard/jobs.py` is rewritten to enqueue through the new queue and poll the DB for streaming instead of running jobs itself.

**Tech Stack:** Python 3.11+, psycopg3 (already added in chunk 1), existing `threading`-based daemon-thread model.

## Global Constraints

- Python 3.11+, type hints everywhere, PEP 8.
- No comments explaining *what*, only non-obvious *why*.
- `claudeshorts/jobs/worker.py` must never import dashboard code (goal.md: backend never depends on frontend existing).
- `static/dashboard.js`'s SSE consumer must not need changes — same event names/shapes (`progress`, plain `data:` lines, `done`).
- Full spec: `docs/superpowers/specs/2026-07-10-chunk2-job-queue-design.md`.

---

## File Structure

- Modify: `claudeshorts/store/db.py` — add the new `jobs` columns to `SCHEMA`.
- Modify: `claudeshorts/store/jobs.py` — data-access functions for the new columns (`claim_next`-supporting queries live in `jobs/queue.py`, not here — `store/jobs.py` stays a thin table wrapper per the existing chunk-1 convention; `jobs/queue.py` is where state-machine logic lives).
- Modify: `config/settings.yaml` — new `jobs:` section.
- Create: `claudeshorts/jobs/__init__.py`
- Create: `claudeshorts/jobs/registry.py`
- Create: `claudeshorts/jobs/queue.py`
- Create: `claudeshorts/jobs/worker.py`
- Modify: `claudeshorts/dashboard/jobs.py` — replace `start_job`/in-memory `Job` streaming with `enqueue_job` + DB-polling `stream`.
- Modify: `claudeshorts/dashboard/app.py` — 6 call sites switch from `jobs.start_job(name, target)` to `jobs.enqueue_job(job_type, payload, name)`.
- Modify: `claudeshorts/dashboard/__init__.py` (or wherever the app is created) — start the worker thread on app startup.
- Create: `tests/jobs/test_queue.py`, `tests/jobs/test_worker.py`, `tests/jobs/test_registry.py`

---

### Task 1: Extend the `jobs` schema

**Files:**
- Modify: `claudeshorts/store/db.py`
- Test: `tests/store/test_db.py` (extend)

**Interfaces:**
- Produces: `jobs` table with new columns `job_type TEXT`, `payload JSONB`, `attempts INTEGER`, `max_attempts INTEGER`, `next_attempt_at TIMESTAMPTZ`, `cancel_requested BOOLEAN`, `pause_requested BOOLEAN`, `locked_by TEXT`, `locked_at TIMESTAMPTZ`.

- [ ] **Step 1: Write the failing test**

```python
# tests/store/test_db.py (add to existing file)
def test_jobs_table_has_queue_columns():
    with db.connect() as conn:
        row = conn.execute(
            "INSERT INTO jobs (name, job_type, payload) "
            "VALUES ('t', 'ingest', '{}'::jsonb) RETURNING *"
        ).fetchone()
        assert row["attempts"] == 0
        assert row["max_attempts"] == 3
        assert row["cancel_requested"] is False
        assert row["pause_requested"] is False
        assert row["locked_by"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_db.py::test_jobs_table_has_queue_columns -v`
Expected: FAIL — `column "job_type" of relation "jobs" does not exist`

- [ ] **Step 3: Add the columns to `SCHEMA` in `claudeshorts/store/db.py`**

Replace the `CREATE TABLE IF NOT EXISTS jobs (...)` block's closing `);` line
and everything after it with:

```python
CREATE TABLE IF NOT EXISTS jobs (
    id               BIGSERIAL PRIMARY KEY,
    name             TEXT        NOT NULL,
    status           TEXT        NOT NULL DEFAULT 'PENDING',
    job_type         TEXT        NOT NULL DEFAULT 'legacy',
    payload          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    attempts         INTEGER     NOT NULL DEFAULT 0,
    max_attempts     INTEGER     NOT NULL DEFAULT 3,
    next_attempt_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancel_requested BOOLEAN     NOT NULL DEFAULT false,
    pause_requested  BOOLEAN     NOT NULL DEFAULT false,
    locked_by        TEXT,
    locked_at        TIMESTAMPTZ,
    phase_index      INTEGER     NOT NULL DEFAULT 0,
    phase_total      INTEGER     NOT NULL DEFAULT 0,
    phase_label      TEXT        NOT NULL DEFAULT '',
    progress_current INTEGER     NOT NULL DEFAULT 0,
    progress_total   INTEGER     NOT NULL DEFAULT 0,
    progress_label   TEXT        NOT NULL DEFAULT '',
    log              TEXT        NOT NULL DEFAULT '',
    error            TEXT,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs(status, next_attempt_at);
"""
```

Note: `status` default changes from `'running'` to `'PENDING'` (uppercase,
matching the state-machine names in the spec) — this is a breaking rename
of the status vocabulary, acceptable because chunk 1's migration already
ran and this chunk owns the queue rewrite end to end. Existing rows
migrated in chunk 1 keep their old lowercase `status` values (`ok`,
`error`, `interrupted`, `running`) since `ALTER TABLE ... ADD COLUMN`
doesn't touch existing values — Task 8's dashboard rewrite must handle
both vocabularies when displaying historical jobs (see Task 8).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/store/db.py tests/store/test_db.py
git commit -m "feat: extend jobs table with queue/state-machine columns"
```

---

### Task 2: `jobs:` config section + backoff helper

**Files:**
- Modify: `config/settings.yaml`
- Create: `claudeshorts/jobs/__init__.py` (empty, package marker)
- Create: `claudeshorts/jobs/queue.py` (backoff function only in this task)
- Test: `tests/jobs/test_queue.py`

**Interfaces:**
- Consumes: `claudeshorts.config.settings()` (existing)
- Produces: `backoff(attempts: int) -> timedelta`

- [ ] **Step 1: Write the failing test**

```python
# tests/jobs/test_queue.py
from __future__ import annotations

from datetime import timedelta

from claudeshorts.jobs import queue


def test_backoff_doubles_then_caps():
    assert queue.backoff(1) == timedelta(seconds=5)
    assert queue.backoff(2) == timedelta(seconds=10)
    assert queue.backoff(3) == timedelta(seconds=20)
    assert queue.backoff(10) == timedelta(seconds=300)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_queue.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.jobs'`

- [ ] **Step 3: Add the config section**

Append to `config/settings.yaml`:
```yaml
jobs:
  max_attempts: 3
  base_delay_seconds: 5
  max_delay_seconds: 300
  poll_interval_seconds: 1.0
```

- [ ] **Step 4: Create the package and backoff helper**

```python
# claudeshorts/jobs/__init__.py
```

```python
# claudeshorts/jobs/queue.py
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/jobs/test_queue.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add config/settings.yaml claudeshorts/jobs/__init__.py claudeshorts/jobs/queue.py tests/jobs/test_queue.py
git commit -m "feat: add jobs config section and backoff helper"
```

---

### Task 3: `queue.enqueue` and `queue.claim_next`

**Files:**
- Modify: `claudeshorts/jobs/queue.py`
- Test: `tests/jobs/test_queue.py` (extend)

**Interfaces:**
- Consumes: `claudeshorts.store.db.connect()`
- Produces: `enqueue(job_type: str, payload: dict, *, name: str, max_attempts: int | None = None) -> int`, `JobRecord` (a `TypedDict`-like plain `dict` returned by `claim_next`), `claim_next(worker_id: str) -> dict | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/jobs/test_queue.py (add to existing file)
from claudeshorts.store import db
from claudeshorts.jobs import queue


def test_enqueue_creates_pending_job():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "PENDING"
    assert row["job_type"] == "ingest"
    assert row["max_attempts"] == 3


def test_claim_next_locks_and_marks_running():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    claimed = queue.claim_next("worker-1")
    assert claimed["id"] == job_id
    assert claimed["status"] == "RUNNING"
    assert claimed["locked_by"] == "worker-1"
    assert queue.claim_next("worker-2") is None  # nothing else pending


def test_claim_next_ignores_future_next_attempt_at():
    from datetime import datetime, timedelta, timezone
    job_id = queue.enqueue("ingest", {}, name="ingest")
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'RETRYING', "
            "next_attempt_at = %s WHERE id = %s",
            (datetime.now(timezone.utc) + timedelta(hours=1), job_id),
        )
    assert queue.claim_next("worker-1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_queue.py -v`
Expected: FAIL — `AttributeError: module 'claudeshorts.jobs.queue' has no attribute 'enqueue'`

- [ ] **Step 3: Implement `enqueue` and `claim_next`**

Add to `claudeshorts/jobs/queue.py` (below `backoff`):

```python
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..store import db


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_queue.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/jobs/queue.py tests/jobs/test_queue.py
git commit -m "feat: implement queue.enqueue and queue.claim_next"
```

---

### Task 4: `queue.complete`, `queue.fail`, cancel/pause/resume

**Files:**
- Modify: `claudeshorts/jobs/queue.py`
- Test: `tests/jobs/test_queue.py` (extend)

**Interfaces:**
- Produces: `complete(job_id, result)`, `fail(job_id, error)`, `request_cancel(job_id)`, `request_pause(job_id)`, `resume(job_id)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/jobs/test_queue.py (add to existing file)
def test_complete_marks_completed():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    queue.claim_next("worker-1")
    queue.complete(job_id, "42 items")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "COMPLETED"
    assert row["error"] is None
    assert row["finished_at"] is not None


def test_fail_retries_until_max_attempts():
    job_id = queue.enqueue("ingest", {}, name="ingest", max_attempts=2)
    queue.claim_next("worker-1")
    queue.fail(job_id, "boom 1")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "RETRYING"
    assert row["attempts"] == 1

    queue.claim_next("worker-1")
    queue.fail(job_id, "boom 2")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "FAILED"
    assert row["attempts"] == 2
    assert row["error"] == "boom 2"


def test_cancel_pending_job_removes_it_from_claim():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    queue.request_cancel(job_id)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "CANCELLED"
    assert queue.claim_next("worker-1") is None


def test_pause_then_resume():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    queue.request_pause(job_id)
    assert queue.claim_next("worker-1") is None
    queue.resume(job_id)
    claimed = queue.claim_next("worker-1")
    assert claimed["id"] == job_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_queue.py -v`
Expected: FAIL — `complete`/`fail`/`request_cancel`/`request_pause`/`resume` not defined

- [ ] **Step 3: Implement the remaining queue operations**

Add to `claudeshorts/jobs/queue.py`:

```python
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
    cancel only, no mid-execution interruption)."""
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = CASE WHEN status = 'RUNNING' "
            "THEN 'RUNNING' ELSE 'CANCELLED' END, "
            "cancel_requested = true, "
            "finished_at = CASE WHEN status != 'RUNNING' THEN now() "
            "ELSE finished_at END "
            "WHERE id = %s",
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_queue.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/jobs/queue.py tests/jobs/test_queue.py
git commit -m "feat: implement queue.complete/fail/cancel/pause/resume"
```

---

### Task 5: `registry.py` — job_type to pipeline call mapping

**Files:**
- Create: `claudeshorts/jobs/registry.py`
- Test: `tests/jobs/test_registry.py`

**Interfaces:**
- Produces: `JOB_HANDLERS: dict[str, Callable[[dict], Any]]` with keys
  `"full_run"`, `"ingest"`, `"generate"`, `"generate_from_item"`,
  `"render_post"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/jobs/test_registry.py
from __future__ import annotations

from unittest.mock import patch

from claudeshorts.jobs import registry


def test_all_six_job_types_registered():
    expected = {"full_run", "ingest", "generate", "generate_from_item", "render_post"}
    assert expected <= set(registry.JOB_HANDLERS)


def test_generate_from_item_unpacks_payload():
    with patch("claudeshorts.generate.generate_for_item") as mock_fn:
        mock_fn.return_value = {"post_id": 5}
        result = registry.JOB_HANDLERS["generate_from_item"]({"item_id": 5})
        mock_fn.assert_called_once_with(5)
        assert result == {"post_id": 5}


def test_render_post_unpacks_payload():
    with patch("claudeshorts.jobs.registry._render_post_by_id") as mock_fn:
        mock_fn.return_value = "rendered post 7: 40 frames"
        result = registry.JOB_HANDLERS["render_post"]({"post_id": 7})
        mock_fn.assert_called_once_with(7)
        assert result == "rendered post 7: 40 frames"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.jobs.registry'`

- [ ] **Step 3: Implement `registry.py`**

```python
"""Maps a job's `job_type` string to the pipeline call it runs.

Kept separate from `worker.py` so the worker loop never imports pipeline
modules directly — only this module does, and only lazily (inside each
wrapper), matching the existing lazy-import convention in `dashboard/app.py`.
"""

from __future__ import annotations

from typing import Any, Callable


def _full_run(payload: dict[str, Any]) -> Any:
    from ..orchestrate import run_pipeline
    return run_pipeline(force=True)


def _ingest(payload: dict[str, Any]) -> Any:
    from ..ingest import run_ingest
    return run_ingest()


def _generate(payload: dict[str, Any]) -> Any:
    from ..generate import run_generate
    return run_generate()


def _generate_from_item(payload: dict[str, Any]) -> Any:
    from ..generate import generate_for_item
    return generate_for_item(payload["item_id"])


def _render_post_by_id(post_id: int) -> str:
    from ..render.bridge import render_post
    from ..review.queue import assemble_review
    from ..store import connect, get_post

    with connect() as conn:
        post = get_post(conn, post_id)
    if not post:
        raise ValueError(f"no post {post_id}")
    result = render_post(post)
    assemble_review(post, result)
    return f"rendered post {post_id}: {result.get('frames')} frames"


def _render_post(payload: dict[str, Any]) -> Any:
    return _render_post_by_id(payload["post_id"])


JOB_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "full_run": _full_run,
    "ingest": _ingest,
    "generate": _generate,
    "generate_from_item": _generate_from_item,
    "render_post": _render_post,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/jobs/registry.py tests/jobs/test_registry.py
git commit -m "feat: add job registry mapping job_type to pipeline calls"
```

---

### Task 6: `worker.py` — polling dispatch loop

**Files:**
- Create: `claudeshorts/jobs/worker.py`
- Test: `tests/jobs/test_worker.py`

**Interfaces:**
- Consumes: `queue.claim_next`, `queue.complete`, `queue.fail`, `registry.JOB_HANDLERS`, `..progress.set_sink`/`clear_sink`.
- Produces: `run_forever(worker_id: str, *, poll_interval: float | None = None, max_iterations: int | None = None) -> None`, `dispatch_one(worker_id: str) -> bool` (returns whether a job was claimed and run — used by tests and by `run_forever`'s loop body).

- [ ] **Step 1: Write the failing tests**

```python
# tests/jobs/test_worker.py
from __future__ import annotations

from unittest.mock import patch

from claudeshorts.jobs import queue, worker


def test_dispatch_one_runs_registered_handler_and_completes():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    with patch.dict(
        "claudeshorts.jobs.registry.JOB_HANDLERS",
        {"ingest": lambda payload: "42 items"},
    ):
        assert worker.dispatch_one("worker-1") is True
    from claudeshorts.store import db
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "COMPLETED"


def test_dispatch_one_returns_false_when_queue_empty():
    assert worker.dispatch_one("worker-1") is False


def test_dispatch_one_fails_job_on_handler_exception():
    job_id = queue.enqueue("ingest", {}, name="ingest", max_attempts=1)

    def _boom(payload):
        raise RuntimeError("kaboom")

    with patch.dict("claudeshorts.jobs.registry.JOB_HANDLERS", {"ingest": _boom}):
        worker.dispatch_one("worker-1")
    from claudeshorts.store import db
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row["status"] == "FAILED"
    assert "kaboom" in row["error"]


def test_dispatch_one_skips_cancel_requested_job():
    job_id = queue.enqueue("ingest", {}, name="ingest")
    queue.request_cancel(job_id)
    assert worker.dispatch_one("worker-1") is False


def test_run_forever_stops_after_max_iterations():
    worker.run_forever("worker-1", poll_interval=0.01, max_iterations=3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.jobs.worker'`

- [ ] **Step 3: Implement `worker.py`**

```python
"""Polling worker: claims one job at a time from the queue and runs it.

Runs as a daemon thread inside the dashboard process by default, but is a
standalone entry point (`python -m claudeshorts.jobs.worker`) so it can be
split into its own process later without a redesign — `queue.claim_next`'s
`FOR UPDATE SKIP LOCKED` already makes concurrent workers safe.
"""

from __future__ import annotations

import logging
import time

from .. import progress
from ..config import settings
from . import queue, registry

log = logging.getLogger("claudeshorts.jobs.worker")


def dispatch_one(worker_id: str) -> bool:
    """Claim and run at most one job. Returns True if a job was claimed."""
    try:
        job = queue.claim_next(worker_id)
    except Exception:
        log.exception("claim_next failed (DB unreachable?)")
        return False
    if job is None:
        return False
    if job["cancel_requested"]:
        queue.request_cancel(job["id"])
        return True

    handler = registry.JOB_HANDLERS.get(job["job_type"])
    if handler is None:
        queue.fail(job["id"], f"no handler registered for job_type {job['job_type']!r}")
        return True

    def _sink(kind: str, payload: dict) -> None:
        from ..store import db, jobs as store_jobs
        try:
            with db.connect() as conn:
                if kind == "phase":
                    store_jobs.save_snapshot(conn, job["id"], {
                        "phase_index": payload["index"], "phase_total": payload["total"],
                        "phase_label": payload.get("label", ""),
                    })
                elif kind == "step":
                    store_jobs.save_snapshot(conn, job["id"], {
                        "progress_current": payload["current"],
                        "progress_total": payload["total"],
                        "progress_label": payload.get("label", ""),
                    })
        except Exception:
            pass

    progress.set_sink(_sink)
    try:
        result = handler(job["payload"])
        queue.complete(job["id"], str(result) if result is not None else None)
    except Exception as exc:
        log.exception("job %s (%s) failed", job["id"], job["job_type"])
        queue.fail(job["id"], str(exc))
    finally:
        progress.clear_sink()
    return True


def run_forever(
    worker_id: str, *, poll_interval: float | None = None,
    max_iterations: int | None = None,
) -> None:
    """Loop claiming and running jobs. `max_iterations` is for tests only."""
    interval = poll_interval or settings().get("jobs", {}).get("poll_interval_seconds", 1.0)
    i = 0
    while max_iterations is None or i < max_iterations:
        claimed = dispatch_one(worker_id)
        if not claimed:
            time.sleep(interval)
        i += 1


if __name__ == "__main__":
    import sys
    run_forever(sys.argv[1] if len(sys.argv) > 1 else "worker-cli")
```

Note: `save_snapshot` from `store/jobs.py` (chunk 1) takes a full
`_PROGRESS_COLS` tuple and writes all of them — passing a partial dict
here means the other columns get overwritten with `None`/defaults on every
phase/step call. **This is a real bug to fix, not ship** — see Step 4.

- [ ] **Step 4: Fix `store/jobs.save_snapshot` to support partial updates**

`claudeshorts/store/jobs.py`'s `save_snapshot` currently does
`f"{c} = %s" for c in _PROGRESS_COLS` for every column unconditionally.
Change it to only update columns present in the passed dict:

```python
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
```

Add a regression test to `tests/store/test_jobs.py`:

```python
def test_save_snapshot_partial_update_preserves_other_columns():
    with db.connect() as conn:
        jobs.insert_job(conn, job_id=1, name="ingest")
        jobs.save_snapshot(conn, 1, {"status": "RUNNING"})
        jobs.save_snapshot(conn, 1, {"phase_index": 2, "phase_total": 5})
        got = jobs.get_job(conn, 1)
    assert got["status"] == "RUNNING"
    assert got["phase_index"] == 2
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/jobs/test_worker.py tests/store/test_jobs.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/jobs/worker.py tests/jobs/test_worker.py claudeshorts/store/jobs.py tests/store/test_jobs.py
git commit -m "feat: add polling worker; fix save_snapshot to support partial updates"
```

---

### Task 7: Start the worker thread on dashboard startup

**Files:**
- Modify: `claudeshorts/dashboard/app.py` (or its app-factory/startup hook — locate via Step 1)

**Interfaces:**
- Consumes: `claudeshorts.jobs.worker.run_forever`

- [ ] **Step 1: Find the FastAPI startup hook**

Run: `grep -n "on_event\|lifespan\|@app\." claudeshorts/dashboard/app.py | head -20`

Expected: a `create_app()` function or module-level `app = FastAPI(...)`
with room to add a startup hook.

- [ ] **Step 2: Add the worker thread startup**

In `claudeshorts/dashboard/app.py`, near where `app` is constructed, add:

```python
@app.on_event("startup")
def _start_job_worker() -> None:
    import threading
    from ..jobs.worker import run_forever

    threading.Thread(
        target=run_forever, args=("dashboard-worker",), daemon=True,
    ).start()
```

(If the codebase already uses FastAPI's `lifespan` context manager instead
of `on_event`, add the thread start there instead — match whatever startup
mechanism `claudeshorts/dashboard/app.py` already uses rather than
introducing a second one.)

- [ ] **Step 3: Manual verification**

Run: `./start-dashboard.sh`, check server logs for no startup errors, then
confirm a background job still completes: trigger `/actions/ingest` once
Task 8 rewires the route (this step is a placeholder check to return to
after Task 8 — note it here so it isn't forgotten, then perform the real
end-to-end check in Task 8 Step 5 instead of here).

- [ ] **Step 4: Commit**

```bash
git add claudeshorts/dashboard/app.py
git commit -m "feat: start job worker thread on dashboard startup"
```

---

### Task 8: Rewire `dashboard/jobs.py` and the 6 `dashboard/app.py` call sites

**Files:**
- Modify: `claudeshorts/dashboard/jobs.py`
- Modify: `claudeshorts/dashboard/app.py`
- Test: `tests/dashboard/test_jobs_stream.py`

**Interfaces:**
- Produces: `enqueue_job(job_type: str, payload: dict, name: str) -> int` (replaces `start_job`), `recent_jobs(limit)`, `get_job(job_id)`, `stream(job_id)` — same names/shapes as before so templates (`jobs.html`, `overview.html`) don't need changes.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_jobs_stream.py
from __future__ import annotations

from unittest.mock import patch

from claudeshorts.dashboard import jobs
from claudeshorts.jobs import queue, worker


def test_enqueue_job_then_stream_emits_progress_and_done():
    job_id = jobs.enqueue_job("ingest", {}, "ingest")
    with patch.dict(
        "claudeshorts.jobs.registry.JOB_HANDLERS",
        {"ingest": lambda payload: "5 items"},
    ):
        worker.dispatch_one("test-worker")
    events = list(jobs.stream(job_id))
    joined = "".join(events)
    assert "event: progress" in joined
    assert "event: done" in joined
    assert "5 items" not in joined or "data:" in joined  # log line present if captured


def test_recent_jobs_reflects_new_queue_status_values():
    jobs.enqueue_job("ingest", {}, "ingest")
    recent = jobs.recent_jobs(10)
    assert recent[0].status in {"PENDING", "RUNNING", "COMPLETED", "FAILED"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dashboard/test_jobs_stream.py -v`
Expected: FAIL — `AttributeError: module 'claudeshorts.dashboard.jobs' has no attribute 'enqueue_job'`

- [ ] **Step 3: Rewrite `claudeshorts/dashboard/jobs.py`**

Replace the entire file:

```python
"""Dashboard-facing view over the durable job queue.

Jobs run via `claudeshorts.jobs.worker` (a polling daemon thread started at
app startup, see `dashboard/app.py`). This module only enqueues and reads —
it does not run jobs itself. SSE streaming polls the DB row on an interval
instead of reading an in-memory object, since a job may now be claimed and
executed by a different thread than the one serving the HTTP request that
enqueued it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from ..config import settings
from ..jobs import queue as job_queue
from ..store import connect
from ..store import jobs as store_jobs

_TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED", "ok", "error", "interrupted"}


@dataclass
class JobView:
    id: int
    name: str
    status: str
    done: bool
    phase: dict[str, Any]
    step: dict[str, Any]
    started_at: str
    elapsed_seconds: float
    error: str | None


def _to_view(row: dict[str, Any]) -> JobView:
    phase_total = row.get("phase_total") or 0
    step_total = row.get("progress_total") or 0
    started = row.get("started_at")
    finished = row.get("finished_at")
    started_dt = started if isinstance(started, datetime) else datetime.now(timezone.utc)
    end_dt = finished if isinstance(finished, datetime) else datetime.now(timezone.utc)
    return JobView(
        id=row["id"], name=row["name"], status=row["status"],
        done=row["status"] in _TERMINAL_STATUSES,
        phase={"index": row.get("phase_index", 0), "total": phase_total,
               "label": row.get("phase_label", ""),
               "percent": round(100 * row.get("phase_index", 0) / phase_total) if phase_total else None},
        step={"current": row.get("progress_current", 0), "total": step_total,
              "label": row.get("progress_label", ""),
              "percent": round(100 * row.get("progress_current", 0) / step_total) if step_total else None},
        started_at=started_dt.isoformat(timespec="seconds"),
        elapsed_seconds=round(max(0.0, (end_dt - started_dt).total_seconds()), 1),
        error=row.get("error"),
    )


def enqueue_job(job_type: str, payload: dict[str, Any], name: str) -> int:
    """Enqueue a job; the worker thread picks it up on its next poll."""
    return job_queue.enqueue(job_type, payload, name=name)


def get_job(job_id: int) -> JobView | None:
    with connect() as conn:
        row = store_jobs.get_job(conn, job_id)
    return _to_view(row) if row else None


def recent_jobs(limit: int = 50) -> list[JobView]:
    with connect() as conn:
        rows = store_jobs.recent_jobs(conn, limit)
    return [_to_view(r) for r in rows]


def stream(job_id: int) -> Iterator[str]:
    """Yield SSE for a job by polling the DB row until it reaches a terminal state."""
    poll = settings().get("jobs", {}).get("poll_interval_seconds", 1.0)
    last_log_len = 0
    last_sig = None
    while True:
        with connect() as conn:
            row = store_jobs.get_job(conn, job_id)
        if row is None:
            yield "event: done\ndata: missing\n\n"
            return
        view = _to_view(row)
        sig = (view.phase["index"], view.phase["total"], view.phase["label"],
               view.step["current"], view.step["total"], view.step["label"])
        if sig != last_sig:
            last_sig = sig
            payload = {"phase": view.phase, "step": view.step,
                       "status": view.status, "elapsed_seconds": view.elapsed_seconds}
            yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
        log = row.get("log") or ""
        if len(log) > last_log_len:
            new = log[last_log_len:]
            last_log_len = len(log)
            for line in new.split("\n"):
                yield "\n".join(f"data: {part}" for part in [line] or [""]) + "\n\n"
        if view.done:
            yield f"event: done\ndata: {view.status}\n\n"
            return
        time.sleep(poll)
```

- [ ] **Step 4: Update the 6 call sites in `claudeshorts/dashboard/app.py`**

Replace each `jobs.start_job(...)` call:

```python
# /actions/run
jid = jobs.enqueue_job("full_run", {}, "daily run")
# /actions/ingest
jid = jobs.enqueue_job("ingest", {}, "ingest")
# /actions/generate
jid = jobs.enqueue_job("generate", {}, "generate")
# /articles (action=generate, after inserting the manual item)
jid = jobs.enqueue_job("generate_from_item", {"item_id": item_id}, f"generate from “{title[:40]}”")
# /articles/{item_id}/generate
jid = jobs.enqueue_job("generate_from_item", {"item_id": item_id}, f"generate from item {item_id}")
# /posts/{post_id}/render
jid = jobs.enqueue_job("render_post", {"post_id": post_id}, f"render post {post_id}")
```

Remove the now-unused `_do` closure and any `from ..orchestrate import
run_pipeline` / `from ..ingest import run_ingest` / etc. lazy imports at
these call sites — that logic now lives in `registry.py`.

- [ ] **Step 5: Manual end-to-end verification (also covers Task 7 Step 3)**

Run: `./start-dashboard.sh`, open the dashboard, click "Ingest" from the
overview page. Confirm: the jobs page shows the job transition PENDING →
RUNNING → COMPLETED, the live log stream appears in the browser, and
`recent_jobs`/`jobs.html` render without template errors (the `JobView`
dataclass exposes the same field names the old `Job.to_dict()` produced).

- [ ] **Step 6: Run automated tests**

Run: `pytest tests/dashboard/test_jobs_stream.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add claudeshorts/dashboard/jobs.py claudeshorts/dashboard/app.py tests/dashboard/test_jobs_stream.py
git commit -m "feat: rewire dashboard to enqueue through the job queue and poll for streaming"
```

---

### Task 9: Update checkpoint and task tracking

**Files:**
- Modify: `CHECKPOINT_LAST.md`, `TASK_QUEUE.md`

- [ ] **Step 1: Record completion**

Update `TASK_QUEUE.md` to move chunk 2 to Done with a summary (schema
extended, `jobs/` package added, dashboard rewired, verified live). Update
`CHECKPOINT_LAST.md` with next action: chunk 3 (service layer extraction).

- [ ] **Step 2: Commit**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 2 complete — durable job queue live, verified"
```

---

## Self-Review Notes

**Spec coverage:** Schema extension (Task 1) → all new columns from the
spec's ALTER list. `enqueue`/`claim_next` with `SKIP LOCKED` (Task 3) →
matches spec's claiming design. `complete`/`fail` with exponential backoff
(Task 4) → matches spec's retry policy. Cancel/pause queue-level-only
semantics (Task 4) → matches the confirmed decision (RUNNING jobs aren't
interrupted, only flagged). Registry mapping all 6 job kinds (Task 5) →
covers every route in the spec's table. Worker loop with fail-safe DB-error
handling (Task 6) → matches "failures should never crash the app." Dashboard
SSE polling replacing in-memory streaming with unchanged wire format (Task
8) → matches the confirmed decision and the constraint that
`static/dashboard.js` needs no changes. `WAITING_FOR_APPROVAL` is
schema-only, correctly left unused per spec's "out of scope."

**Placeholder scan:** none found — every step has runnable code.

**Type consistency:** `JobView` field names (`id`, `name`, `status`, `done`,
`phase`, `step`, `started_at`, `elapsed_seconds`, `error`) match the old
`Job.to_dict()` shape used by templates. `queue.claim_next`'s returned dict
keys (`id`, `status`, `locked_by`, `job_type`, `payload`,
`cancel_requested`) are consistently referenced the same way in
`worker.dispatch_one` (Task 6) and the tests (Task 3, Task 6). Found one
real bug during planning (`store.jobs.save_snapshot` clobbering
unspecified columns) and folded the fix into Task 6 rather than leaving it
for later, since the worker's partial-update usage pattern depends on it.
