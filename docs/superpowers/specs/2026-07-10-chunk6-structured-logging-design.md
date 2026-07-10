# Chunk 6: Structured logging overhaul

## Context

Sixth of 14 chunks rebuilding claudeshorts per `goal.md` (see `TASK_QUEUE.md`
/ session task list). goal.md's Logging section requires structured logs
carrying timestamps, job id, worker id, profile, platform, duration, and
error details, and says to avoid `print()` in favor of Python `logging`.

## Current state

The codebase already avoids bare `print()` everywhere except the CLI's
intentional `typer.echo` (correct — that's user-facing terminal output, not
a log). Three modules use `logging.getLogger`:
`claudeshorts/generate/runner.py`, `claudeshorts/orchestrate/runner.py`,
`claudeshorts/dashboard/jobs.py`. Each configures logging independently:
`orchestrate/runner.py::setup_logging()` calls `logging.basicConfig` with
a plain `"%(asctime)s %(levelname)s %(message)s"` format, only when no
handlers exist yet and only when `run_pipeline` is invoked;
`dashboard/jobs.py` separately installs its own `_JobLogHandler` with its
own formatter, routing records to whichever job owns the emitting thread.
Neither carries structured fields (job id, worker id, platform) — job id
is sometimes embedded in a free-text message (`"rendered + queued post
%d"`), never as a queryable field.

Chunks 2 (jobs) and 5 (scheduling) introduced real job ids and worker ids
that don't yet flow into log records at all outside the dashboard's
thread-routing trick, and `publish/exporter.py` loops over platforms
without tagging which platform a given log line belongs to.

## Decision (confirmed with user)

One `claudeshorts/logging_setup.py`, called once from every process entry
point (CLI's `app()` callback, `dashboard/app.py`'s `create_app()`,
`jobs/worker.py`'s `__main__`, `scheduling/scheduler.py`'s `__main__`),
replacing `orchestrate/runner.py::setup_logging()` and
`dashboard/jobs.py`'s bespoke handler/formatter setup:

- A `logging.Filter` populates `job_id`/`worker_id`/`platform` fields (from
  `contextvars.ContextVar`s, default `None`) onto every `LogRecord` so
  `%(job_id)s` etc. are always available in the format string, whether or
  not the emitting code bound them.
- A `bind(job_id=None, worker_id=None, platform=None)` context manager sets
  those contextvars for the duration of a `with` block — used around each
  job dispatch in `jobs/worker.py`, and around each platform in
  `publish/exporter.py`'s export loop.
- **Plain text stays the default** (human-readable local dev/CLI use);
  **JSON is a config toggle** (`config/settings.yaml`'s new `logging:
  format: text|json`) for the Raspberry Pi/headless case, where logs are
  more likely to be tailed/aggregated by another tool than read directly
  in a terminal.
- Duration is logged explicitly at the point work completes (job
  dispatch, platform export), not derived by a generic timer wrapper —
  simpler and matches how `jobs.queue.complete`/`fail` already know when a
  job started (`started_at` column).

## Architecture

### `claudeshorts/logging_setup.py`

```python
import contextvars, logging

_job_id: ContextVar[int | None] = ContextVar("job_id", default=None)
_worker_id: ContextVar[str | None] = ContextVar("worker_id", default=None)
_platform: ContextVar[str | None] = ContextVar("platform", default=None)

class _ContextFilter(logging.Filter):
    def filter(self, record):
        record.job_id = _job_id.get()
        record.worker_id = _worker_id.get()
        record.platform = _platform.get()
        return True

@contextmanager
def bind(*, job_id=None, worker_id=None, platform=None): ...

def configure_logging(level=logging.INFO) -> None: ...
```

`configure_logging()` is idempotent (checks for its own sentinel attribute
on the root `claudeshorts` logger before attaching handlers again, same
guard style `orchestrate/runner.py::setup_logging` already uses) so it's
safe to call from multiple entry points if a future chunk ends up running
CLI code inside the dashboard process or vice versa.

### Format strings

- Text (default): `"%(asctime)s %(levelname)s [job=%(job_id)s
  worker=%(worker_id)s platform=%(platform)s] %(name)s: %(message)s"` —
  fields print as literal `None` when unbound, which is acceptable/legible
  for local dev (a future chunk could suppress unbound fields if this
  proves noisy in practice; not addressed here to avoid over-engineering
  before real usage feedback exists).
- JSON: one `json.dumps({...})` per record via a custom
  `logging.Formatter` subclass, same field set plus `message`, `level`,
  `logger`, `timestamp`.

### Call-site changes

- `jobs/worker.py::dispatch_one` wraps the handler call in `with
  logging_setup.bind(job_id=job["id"], worker_id=worker_id):` and logs
  `log.info("job %s (%s) completed in %.1fs", ...)` /
  `log.error("job %s (%s) failed after %.1fs: %s", ...)` using
  `time.monotonic()` deltas around the handler call — this is the
  "duration" field goal.md asks for, computed explicitly rather than via a
  generic decorator (YAGNI: only two call sites need it right now).
- `publish/exporter.py::export_post`'s per-platform loop wraps each
  iteration in `with logging_setup.bind(platform=platform):`.
- `dashboard/jobs.py::_JobLogHandler`/`_install_handler` are deleted;
  dashboard startup calls `logging_setup.configure_logging()` instead, and
  per-job log capture for the SSE stream now reads from the `jobs.log`
  column the same way chunk 2's worker already persists it — no separate
  thread-routing handler is needed since `bind(job_id=...)` plus the
  shared root logger already gets every log line onto the record, and
  chunk 2's `save_snapshot` already writes accumulated log text to the DB.
  (This removes real, if modest, duplicate machinery — the `_thread_job`
  dict and `_JobLogHandler` class — since contextvars replace what
  thread-ident routing was working around.)

## Out of scope for this chunk

- "profile" field population — no browser-profile objects exist yet
  (chunk 11, deferred); the `bind()` API accepts a `profile` kwarg from day
  one (cheap to add now) but nothing calls it with a real value until
  chunk 11.
- Log aggregation/shipping (to a file, syslog, or an external service) —
  only console output is configured; where that console output goes on a
  real Raspberry Pi deployment (systemd journal, redirected file) is a
  deployment concern, not a code concern, addressed if/when deployment
  chunks need it.
- Changing log *levels* or adding new log statements beyond what's needed
  to demonstrate `job_id`/`worker_id`/`platform`/duration are wired
  correctly — this chunk is about the plumbing, not an audit of what
  should be logged where.

## Testing

`tests/test_logging_setup.py` — `bind()` correctly scopes contextvars
(nested binds restore outer values on exit), the filter attaches `None`
when unbound, both text and JSON formatters produce parseable output.
Updated `tests/jobs/test_worker.py` and a new
`tests/publish/test_exporter_logging.py` assert `job_id`/`platform` appear
on captured log records via `caplog`.
