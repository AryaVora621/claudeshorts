# Chunk 6: Structured Logging Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace three independent ad hoc logging setups with one `claudeshorts/logging_setup.py` providing contextvar-based `job_id`/`worker_id`/`platform` fields on every log record, a `bind()` context manager, and a text/JSON format toggle.

**Architecture:** A `logging.Filter` reads `contextvars.ContextVar`s and stamps them onto each `LogRecord`; `configure_logging()` attaches one handler+formatter to the `"claudeshorts"` logger, called once per process entry point. `dashboard/jobs.py`'s thread-ident-based log routing is deleted as redundant.

**Tech Stack:** Python 3.11+ stdlib `logging`/`contextvars`/`json`, no new dependencies.

## Global Constraints

- Python 3.11+, type hints everywhere, PEP 8.
- No comments explaining *what*, only non-obvious *why*.
- `configure_logging()` must be idempotent (safe to call more than once).
- Full spec: `docs/superpowers/specs/2026-07-10-chunk6-structured-logging-design.md`.

---

## File Structure

- Create: `claudeshorts/logging_setup.py`
- Modify: `config/settings.yaml` — new `logging:` section
- Modify: `claudeshorts/orchestrate/runner.py` — remove `setup_logging`, call `logging_setup.configure_logging()`
- Modify: `claudeshorts/dashboard/jobs.py` — delete `_JobLogHandler`/`_install_handler`/`_thread_job`
- Modify: `claudeshorts/dashboard/app.py` — call `configure_logging()` at startup
- Modify: `claudeshorts/jobs/worker.py` — bind job_id/worker_id, log duration
- Modify: `claudeshorts/scheduling/scheduler.py` — call `configure_logging()` in `__main__`
- Modify: `claudeshorts/publish/exporter.py` — bind platform per loop iteration
- Modify: `claudeshorts/cli.py` — call `configure_logging()` in the app callback
- Create: `tests/test_logging_setup.py`

---

### Task 1: `logging_setup.py` core (filter, bind, configure_logging)

**Files:**
- Create: `claudeshorts/logging_setup.py`
- Modify: `config/settings.yaml`
- Test: `tests/test_logging_setup.py`

**Interfaces:**
- Produces: `bind(*, job_id=None, worker_id=None, platform=None)` (context manager), `configure_logging(level=logging.INFO) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_logging_setup.py
from __future__ import annotations

import json
import logging

from claudeshorts import logging_setup


def test_bind_sets_and_restores_contextvars():
    with logging_setup.bind(job_id=1, worker_id="w1"):
        record = logging.LogRecord("x", logging.INFO, "", 0, "msg", None, None)
        logging_setup._ContextFilter().filter(record)
        assert record.job_id == 1
        assert record.worker_id == "w1"
        assert record.platform is None
    record2 = logging.LogRecord("x", logging.INFO, "", 0, "msg", None, None)
    logging_setup._ContextFilter().filter(record2)
    assert record2.job_id is None


def test_bind_nests_and_restores_outer_value():
    with logging_setup.bind(job_id=1):
        with logging_setup.bind(job_id=2):
            record = logging.LogRecord("x", logging.INFO, "", 0, "m", None, None)
            logging_setup._ContextFilter().filter(record)
            assert record.job_id == 2
        record = logging.LogRecord("x", logging.INFO, "", 0, "m", None, None)
        logging_setup._ContextFilter().filter(record)
        assert record.job_id == 1


def test_configure_logging_is_idempotent():
    logging_setup.configure_logging()
    handlers_after_first = list(logging.getLogger("claudeshorts").handlers)
    logging_setup.configure_logging()
    assert logging.getLogger("claudeshorts").handlers == handlers_after_first


def test_json_formatter_produces_parseable_output(capsys):
    logging_setup.configure_logging(fmt="json")
    log = logging.getLogger("claudeshorts.test")
    with logging_setup.bind(job_id=5, platform="youtube"):
        log.info("hello")
    captured = capsys.readouterr()
    line = [l for l in captured.err.splitlines() if l.strip()][-1]
    parsed = json.loads(line)
    assert parsed["message"] == "hello"
    assert parsed["job_id"] == 5
    assert parsed["platform"] == "youtube"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_logging_setup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.logging_setup'`

- [ ] **Step 3: Add the config section**

Append to `config/settings.yaml`:
```yaml
logging:
  format: "text"   # "text" (human-readable, default) or "json" (RPi/headless)
  level: "INFO"
```

- [ ] **Step 4: Implement `claudeshorts/logging_setup.py`**

```python
"""One place every entry point (CLI, dashboard, job worker, scheduler)
calls to set up logging. Provides job_id/worker_id/platform as structured
fields on every record via contextvars, so goal.md's "structured logs"
requirement doesn't need every call site to pass extra= manually.
"""

from __future__ import annotations

import contextvars
import json
import logging
from contextlib import contextmanager
from typing import Iterator

from .config import settings

_job_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("job_id", default=None)
_worker_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("worker_id", default=None)
_platform: contextvars.ContextVar[str | None] = contextvars.ContextVar("platform", default=None)


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.job_id = _job_id.get()
        record.worker_id = _worker_id.get()
        record.platform = _platform.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "job_id": getattr(record, "job_id", None),
            "worker_id": getattr(record, "worker_id", None),
            "platform": getattr(record, "platform", None),
        })


_TEXT_FORMAT = (
    "%(asctime)s %(levelname)s [job=%(job_id)s worker=%(worker_id)s "
    "platform=%(platform)s] %(name)s: %(message)s"
)


@contextmanager
def bind(*, job_id: int | None = None, worker_id: str | None = None,
          platform: str | None = None) -> Iterator[None]:
    tokens = []
    if job_id is not None:
        tokens.append((_job_id, _job_id.set(job_id)))
    if worker_id is not None:
        tokens.append((_worker_id, _worker_id.set(worker_id)))
    if platform is not None:
        tokens.append((_platform, _platform.set(platform)))
    try:
        yield
    finally:
        for var, token in tokens:
            var.reset(token)


def configure_logging(level: int | str = logging.INFO, *, fmt: str | None = None) -> None:
    logger = logging.getLogger("claudeshorts")
    if getattr(logger, "_claudeshorts_configured", False):
        return
    cfg = settings().get("logging", {})
    fmt = fmt or cfg.get("format", "text")
    level = cfg.get("level", level)
    handler = logging.StreamHandler()
    handler.addFilter(_ContextFilter())
    handler.setFormatter(_JsonFormatter() if fmt == "json" else logging.Formatter(_TEXT_FORMAT, "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger._claudeshorts_configured = True
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_logging_setup.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/logging_setup.py config/settings.yaml tests/test_logging_setup.py
git commit -m "feat: add unified logging_setup with job_id/worker_id/platform context fields"
```

---

### Task 2: Wire `configure_logging()` into every entry point

**Files:**
- Modify: `claudeshorts/orchestrate/runner.py`
- Modify: `claudeshorts/dashboard/app.py`
- Modify: `claudeshorts/jobs/worker.py`
- Modify: `claudeshorts/scheduling/scheduler.py`
- Modify: `claudeshorts/cli.py`

- [ ] **Step 1: Remove `orchestrate/runner.py::setup_logging` and its call site**

Delete the `setup_logging` function (lines defining it) and its
`setup_logging()` call inside `run_pipeline`. Add near the top-level
imports:
```python
from .. import logging_setup
```
And at the very top of `run_pipeline`'s body (where `setup_logging()` used
to be called), add:
```python
    logging_setup.configure_logging()
```

- [ ] **Step 2: Call it from `dashboard/app.py`'s startup hook**

In the same startup hook that starts the job worker and scheduler threads
(from chunks 2 and 5), add as the first line:
```python
    from .. import logging_setup
    logging_setup.configure_logging()
```

- [ ] **Step 3: Call it from `jobs/worker.py` and `scheduling/scheduler.py`'s `__main__` blocks**

In `claudeshorts/jobs/worker.py`:
```python
if __name__ == "__main__":
    import sys
    from .. import logging_setup
    logging_setup.configure_logging()
    run_forever(sys.argv[1] if len(sys.argv) > 1 else "worker-cli")
```

In `claudeshorts/scheduling/scheduler.py`:
```python
if __name__ == "__main__":
    from .. import logging_setup
    logging_setup.configure_logging()
    seed_default_schedules()
    run_forever()
```

- [ ] **Step 4: Call it from `cli.py`**

In `claudeshorts/cli.py`, add near the top-level imports:
```python
from . import logging_setup
```

Add a Typer callback so it runs before any command:
```python
@app.callback()
def _main() -> None:
    logging_setup.configure_logging()
```

- [ ] **Step 5: Run the full existing test suite to check for regressions**

Run: `pytest tests/ -v -k "not (chunk_manual)"`
Expected: PASS — no test should have depended on the removed
`orchestrate.runner.setup_logging` function directly (grep to confirm: `grep -rn "setup_logging" tests/`).

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/orchestrate/runner.py claudeshorts/dashboard/app.py claudeshorts/jobs/worker.py claudeshorts/scheduling/scheduler.py claudeshorts/cli.py
git commit -m "feat: call configure_logging() from every process entry point"
```

---

### Task 3: Bind job_id/worker_id + duration in the job worker

**Files:**
- Modify: `claudeshorts/jobs/worker.py`
- Test: `tests/jobs/test_worker.py` (extend)

**Interfaces:**
- Consumes: `logging_setup.bind`

- [ ] **Step 1: Write the failing test**

```python
# tests/jobs/test_worker.py (add)
def test_dispatch_one_logs_job_id_and_duration(caplog):
    import logging
    job_id = queue.enqueue("ingest", {}, name="ingest")
    with patch.dict("claudeshorts.jobs.registry.JOB_HANDLERS", {"ingest": lambda p: "ok"}):
        with caplog.at_level(logging.INFO, logger="claudeshorts.jobs.worker"):
            worker.dispatch_one("worker-1")
    matching = [r for r in caplog.records if r.job_id == job_id]
    assert matching
    assert "completed in" in matching[-1].message or "completed in" in matching[-1].getMessage()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_worker.py::test_dispatch_one_logs_job_id_and_duration -v`
Expected: FAIL — no log record carries `job_id` yet, or no "completed in" message exists

- [ ] **Step 3: Update `dispatch_one` in `claudeshorts/jobs/worker.py`**

```python
import time  # already imported; ensure present
from .. import logging_setup

def dispatch_one(worker_id: str) -> bool:
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
    with logging_setup.bind(job_id=job["id"], worker_id=worker_id):
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
        started = time.monotonic()
        try:
            result = handler(job["payload"])
            queue.complete(job["id"], str(result) if result is not None else None)
            log.info("job %s (%s) completed in %.1fs", job["id"], job["job_type"],
                      time.monotonic() - started)
        except Exception as exc:
            log.error("job %s (%s) failed after %.1fs: %s", job["id"], job["job_type"],
                       time.monotonic() - started, exc)
            queue.fail(job["id"], str(exc))
        finally:
            progress.clear_sink()
    return True
```

(This replaces the existing function body from chunk 2's plan — same
control flow, wrapped in `bind()` and with the two new `log.info`/
`log.error` duration lines. `log.exception` in the earlier `claim_next`
except-block stays outside `bind()`, correctly, since no job is claimed at
that point.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_worker.py -v`
Expected: PASS (all, including the new duration test)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/jobs/worker.py tests/jobs/test_worker.py
git commit -m "feat: bind job_id/worker_id and log duration in the job worker"
```

---

### Task 4: Bind platform in `publish/exporter.py`

**Files:**
- Modify: `claudeshorts/publish/exporter.py`
- Test: `tests/publish/test_exporter_logging.py`

**Interfaces:**
- Consumes: `logging_setup.bind`

- [ ] **Step 1: Write the failing test**

```python
# tests/publish/test_exporter_logging.py
from __future__ import annotations

import logging

from claudeshorts import logging_setup
from claudeshorts.publish import exporter


def test_export_post_binds_platform_per_iteration(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(exporter, "_locate_video", lambda post_id: _fake_video(tmp_path))
    monkeypatch.setattr(exporter, "_locate_slides", lambda post_id: [])
    from .. import config as cs_config  # adjust import path if needed in-place
    post = {"id": 1, "captions": {}}

    seen_platforms = []
    log = logging.getLogger("claudeshorts.publish.test")

    def _do_export(post, platforms=None):
        for platform in (platforms or ["youtube"]):
            with logging_setup.bind(platform=platform):
                record = logging.LogRecord("x", logging.INFO, "", 0, "m", None, None)
                logging_setup._ContextFilter().filter(record)
                seen_platforms.append(record.platform)

    _do_export(post, platforms=["youtube", "tiktok"])
    assert seen_platforms == ["youtube", "tiktok"]


def _fake_video(tmp_path):
    p = tmp_path / "video.mp4"
    p.write_bytes(b"fake")
    return p
```

Note: this test exercises the `bind()`-per-platform *pattern* directly
rather than mocking `export_post`'s full filesystem behavior — the goal is
verifying the logging context binds per iteration, not re-testing
`export_post`'s file-copying logic (already covered elsewhere). Adjust the
harness in Step 2 to call the *real* `export_post` with monkeypatched
`_locate_video`/`_locate_slides` if a more end-to-end check is preferred;
either is acceptable as long as it proves platform is bound per loop
iteration.

- [ ] **Step 2: Run test to verify it fails or passes trivially**

Run: `pytest tests/publish/test_exporter_logging.py -v`
Expected: This test as written may pass without touching `exporter.py`
since it doesn't call the real function yet — treat Step 3 as the real
change and rewrite this test in Step 3 to assert against the actual
`export_post` call path via `caplog`, so it's a genuine regression check.

- [ ] **Step 3: Rewrite the test against the real `export_post`, then implement the binding**

```python
# tests/publish/test_exporter_logging.py (replace with)
from __future__ import annotations

import logging

from claudeshorts.publish import exporter


def test_export_post_logs_with_platform_bound(monkeypatch, tmp_path, caplog):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    monkeypatch.setattr(exporter, "_locate_video", lambda post_id: video)
    monkeypatch.setattr(exporter, "_locate_slides", lambda post_id: [])
    post = {"id": 1, "captions": {}}

    with caplog.at_level(logging.INFO, logger="claudeshorts.publish"):
        exporter.export_post(post, platforms=["youtube", "tiktok"])

    platforms_seen = {r.platform for r in caplog.records if getattr(r, "platform", None)}
    assert platforms_seen == {"youtube", "tiktok"}
```

Add a log line inside the per-platform loop in `claudeshorts/publish/exporter.py`
(inside `export_post`, replacing the loop body's opening):

```python
import logging
from .. import logging_setup

log = logging.getLogger("claudeshorts.publish")

# ... inside export_post, wrap the existing per-platform loop body:
for platform in platforms:
    with logging_setup.bind(platform=platform):
        log.info("exporting post %d to %s", post["id"], platform)
        dest = config.PUBLISH_DIR / platform / today / f"post_{post['id']}"
        # ... rest of existing loop body unchanged, still inside this `with` block
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/publish/test_exporter_logging.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/publish/exporter.py tests/publish/test_exporter_logging.py
git commit -m "feat: bind platform context and log per-platform export in publish/exporter.py"
```

---

### Task 5: Remove `dashboard/jobs.py`'s redundant thread-routing handler

**Files:**
- Modify: `claudeshorts/dashboard/jobs.py`
- Test: `tests/dashboard/test_jobs_stream.py` (existing, must still pass)

- [ ] **Step 1: Confirm current state doesn't need the handler anymore**

Run: `grep -n "_JobLogHandler\|_install_handler\|_thread_job" claudeshorts/dashboard/jobs.py`

Per chunk 2's rewrite of `dashboard/jobs.py`, this file already reads job
logs from the DB (`store_jobs.get_job`) rather than an in-memory `Job`
object — confirm the `_JobLogHandler`/`_thread_job`/`_install_handler`
machinery from the original pre-chunk-2 file is actually gone already (it
should be, per chunk 2's Task 8 rewrite). If any of it survived
unintentionally, remove it now — it's fully superseded by `bind()` +
`configure_logging()`'s single shared handler.

- [ ] **Step 2: Run existing dashboard tests to confirm no regression**

Run: `pytest tests/dashboard/ -v`
Expected: PASS

- [ ] **Step 3: Commit (only if Step 1 found something to remove)**

```bash
git add claudeshorts/dashboard/jobs.py
git commit -m "cleanup: remove any residual thread-routing log handler superseded by logging_setup"
```

---

### Task 6: Update checkpoint and task tracking

**Files:**
- Modify: `CHECKPOINT_LAST.md`, `TASK_QUEUE.md`

- [ ] **Step 1: Record completion**

Update `TASK_QUEUE.md` to move chunk 6 to Done. Update `CHECKPOINT_LAST.md`
with next action: chunk 7 (LLM provider abstraction, interface only).

- [ ] **Step 2: Commit**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 6 complete — structured logging unified across all entry points"
```

---

## Self-Review Notes

**Spec coverage:** `logging_setup.py` with contextvar filter, `bind()`,
text/JSON toggle (Task 1) matches the spec exactly. All four entry points
wired (Task 2) matches the spec's "called once from every process entry
point" requirement. job_id/worker_id + duration in the worker (Task 3) and
platform binding in the exporter (Task 4) match the spec's two concrete
call-site changes. Removal of `dashboard/jobs.py`'s thread-routing handler
(Task 5) matches the spec's explicit "this removes real, if modest,
duplicate machinery" note — written defensively (Step 1 confirms rather
than assumes, since chunk 2 may have already removed it).

**Placeholder scan:** none — every step has runnable code. Task 4's test
is deliberately written in two passes (Step 1 a simpler direct check, Step
3 the real regression test) because the first version doesn't touch
`exporter.py` at all and would give false confidence; flagged explicitly
rather than silently shipping a weak test.

**Type consistency:** `bind()`'s keyword names (`job_id`, `worker_id`,
`platform`) match the `_ContextFilter`'s attribute names on `LogRecord`
consistently across Tasks 1, 3, and 4. `configure_logging()`'s idempotency
guard (`logger._claudeshorts_configured`) is the same style already used
by `orchestrate/runner.py`'s old `setup_logging` (`if not
logging.getLogger().handlers`), so the migration in Task 2 doesn't
introduce a new pattern the codebase hasn't already accepted.
