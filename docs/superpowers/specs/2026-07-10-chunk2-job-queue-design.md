# Chunk 2: Job queue + state machine

## Context

Second of 14 chunks rebuilding claudeshorts per `goal.md`'s platform
architecture (see `TASK_QUEUE.md` / session task list for the full order).
Chunk 1 moved the datastore to Supabase Postgres; this chunk turns the
`jobs` table from a best-effort snapshot mirror into the actual source of
truth for running work, per goal.md's "Queue Based Architecture" section:
jobs should support retries, cancellation, pause, resume, scheduling,
logging, and progress reporting, and failures should never crash the app.

## Current state

`claudeshorts/dashboard/jobs.py` runs pipeline actions on daemon threads,
in-memory `Job` dataclasses are the live source of truth while a job runs,
and a snapshot is mirrored into the `jobs` table (best-effort, swallows
errors) purely so a finished job's history survives a server restart. Live
log/progress streaming to the browser (SSE) reads directly from the
in-memory `Job` object's condition variable — the DB is never read for a
job that's still alive in the current process.

Six distinct job kinds exist today, started via `jobs.start_job(name, target)`
where `target` is a zero-arg closure capturing route-handler-local state:

| Route | Call | Payload it needs |
|---|---|---|
| `POST /actions/run` | `run_pipeline(force=True)` | none |
| `POST /actions/ingest` | `run_ingest()` | none |
| `POST /actions/generate` | `run_generate()` | none |
| `POST /articles` (action=generate) | `generate_for_item(item_id)` | `item_id` (after inserting a manual item) |
| `POST /articles/{item_id}/generate` | `generate_for_item(item_id)` | `item_id` |
| `POST /posts/{post_id}/render` | `render_post(post)` + `assemble_review(post, result)` | `post_id` |

Progress/log plumbing (`claudeshorts/progress.py`) is a per-thread sink
(`set_sink`/`clear_sink`/`phase`/`step`) already decoupled from any
consumer — pipeline code doesn't know a dashboard exists. This chunk keeps
that contract as-is.

## Decisions (confirmed with user)

1. **The new queue is the sole source of truth.** No parallel in-memory
   system. The dashboard's SSE streaming is rewired to poll the `jobs`
   table (~1s interval) instead of an in-memory `Job` object. Wire format
   to the browser (`static/dashboard.js`'s SSE consumer) is unchanged, so
   no frontend edits are needed.
2. **Cancel/pause are queue-level only in this chunk.** Requesting
   cancel/pause on a `PENDING` job removes it from consideration
   immediately. Requesting it on a `RUNNING` job records the request and
   flips status once the in-flight call returns, but does **not**
   interrupt the call mid-execution — that requires threading a
   cancellation token through `ingest`/`generate`/`render`/`orchestrate`
   runners, deferred until a real long-running job (e.g. a multi-minute
   render) makes that invasiveness worth it.

## Architecture

### Schema: extend `jobs` (additive, builds on chunk 1's Postgres table)

```
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS job_type TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 3;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS pause_requested BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS locked_by TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ;
```

`status` values expand from `running|ok|error|interrupted` to the full
state machine from goal.md, plus `PAUSED` (needed for the pause/resume
requirement, not in goal.md's literal list but implied by it):
`PENDING`, `RUNNING`, `WAITING_FOR_APPROVAL`, `RETRYING`, `FAILED`,
`COMPLETED`, `CANCELLED`, `PAUSED`.
`WAITING_FOR_APPROVAL` is schema-supported but unused by any of today's 6
job kinds — reserved for a future job type (e.g. a publish step needing
human review) so the column doesn't need another migration later.

### `claudeshorts/jobs/` package (new)

- `registry.py` — `JOB_HANDLERS: dict[str, Callable[[dict], Any]]` mapping
  the 6 job kinds above (`full_run`, `ingest`, `generate`,
  `generate_from_item`, `render_post`) to thin wrapper functions that
  unpack `payload` and call the real pipeline function. Keeps
  `worker.py` from importing pipeline modules directly (goal.md: "no
  service should know implementation details of another").
- `queue.py` — pure data-layer operations on the extended `jobs` table:
  - `enqueue(job_type: str, payload: dict, *, name: str, max_attempts: int = 3) -> int`
  - `claim_next(worker_id: str) -> JobRecord | None` — `SELECT ... WHERE
    status IN ('PENDING','RETRYING') AND next_attempt_at <= now() ORDER BY
    id ASC LIMIT 1 FOR UPDATE SKIP LOCKED`, then marks `RUNNING`,
    `locked_by`, `locked_at`.
  - `complete(job_id: int, result: str | None) -> None` → `COMPLETED`
  - `fail(job_id: int, error: str) -> None` → increments `attempts`; if
    `attempts >= max_attempts`, sets `FAILED`; else sets `RETRYING` with
    `next_attempt_at = now() + backoff(attempts)`.
  - `request_cancel(job_id: int) -> None`, `request_pause(job_id: int) ->
    None`, `resume(job_id: int) -> None` (PAUSED → PENDING).
  - `backoff(attempts: int) -> timedelta` — `min(base_delay * 2 **
    (attempts - 1), max_delay)`, both read from `config.settings()["jobs"]`
    (`base_delay_seconds: 5`, `max_delay_seconds: 300`, `max_attempts: 3`
    — new `jobs:` section in `config/settings.yaml`).
- `worker.py` — polling loop:

  ```python
  def run_forever(worker_id: str, *, poll_interval: float = 1.0) -> None:
      while True:
          try:
              job = queue.claim_next(worker_id)
          except Exception:
              log.exception("claim_next failed (DB unreachable?)")
              time.sleep(poll_interval)
              continue
          if job is None:
              time.sleep(poll_interval)
              continue
          _dispatch(job)

  def _dispatch(job: JobRecord) -> None:
      if job.cancel_requested:
          queue.mark_cancelled(job.id)
          return
      handler = registry.JOB_HANDLERS[job.job_type]
      progress.set_sink(_sink_for(job.id))
      try:
          result = handler(job.payload)
          queue.complete(job.id, str(result) if result is not None else None)
      except Exception as exc:
          queue.fail(job.id, str(exc))
      finally:
          progress.clear_sink()
  ```

  Runs as a daemon thread inside the same dashboard process by default
  (matches today's threading model, needs no extra deployment step on the
  Raspberry Pi), but is a standalone entry point
  (`python -m claudeshorts.jobs.worker`) so it can be split into its own
  process later without a redesign — `claim_next`'s `FOR UPDATE SKIP
  LOCKED` already makes concurrent workers safe.
  `pause_requested` is checked the same way as `cancel_requested`: honored
  at the claim boundary (a `PAUSED` job is simply excluded from
  `claim_next`'s `WHERE status IN (...)` list), not mid-execution.

### `dashboard/jobs.py` changes

- `start_job(name, target)` → replaced by `enqueue_job(job_type, payload,
  name)` at each of the 6 call sites in `dashboard/app.py`, returning the
  new job id immediately (same caller-visible shape as before).
- `stream(job_id)` rewritten to poll `store.jobs.get_job(job_id)` every 1s
  (module-level constant, matches the worker's poll interval so log lines
  appear with comparable latency), diff `log` (compare string length,
  yield only the new suffix) and the progress fields (compare the same
  tuple signature used today) between polls, same SSE event shapes
  (`progress`, `data`, `done`) as the current implementation — so
  `static/dashboard.js` needs zero changes.
- Log capture: `_JobLogHandler` still appends to a per-job in-memory line
  buffer in the worker thread (that plumbing doesn't change — it's how
  `progress.py`'s per-thread sink model already works), and that buffer is
  flushed into the `log` column on the same snapshot cadence as before
  (`_PERSIST_EVERY = 1.0`). What changes is *who reads it* — the SSE
  stream reads the DB column instead of the in-memory object directly,
  because after this chunk a job might be claimed and run by a different
  thread/process than the one serving the HTTP request that started it.

### RPi / resilience

- Poll interval (1s) is configurable via `config/settings.yaml`'s new
  `jobs:` section (`poll_interval_seconds: 1.0`) — can be raised on a
  constrained RPi to cut Postgres query volume.
- `claim_next`/DB errors inside the worker loop are caught and logged,
  never crash the loop (goal.md: "failures should never crash the
  application") — a transient network blip to Supabase just delays the
  next claim attempt.
- Single worker thread by default matches RPi's limited cores; the
  `SKIP LOCKED` claim design means adding a second worker later (same
  process or a separate one) requires no schema or logic change.

## Out of scope for this chunk

- True mid-execution cancellation/pause (cooperative cancellation tokens
  threaded through the 4 pipeline runners) — explicit user decision,
  deferred until a concrete long-running job motivates it.
- Any use of `WAITING_FOR_APPROVAL` — reserved for a future job type.
- Service layer extraction (chunk 3) — `dashboard/app.py` route handlers
  still call `enqueue_job` directly in this chunk; chunk 3 is what moves
  that call behind a shared service so the future REST API/Telegram bot
  don't duplicate it.
- Scheduling engine (chunk 5) — `next_attempt_at` here exists purely for
  retry backoff, not for user-facing scheduled/recurring publishing.

## Testing

Extends chunk 1's `tests/store/` pattern: `tests/jobs/test_queue.py`
against the same live Supabase project (enqueue → claim_next → complete/
fail/retry-backoff/cancel/pause state transitions), and
`tests/jobs/test_worker.py` driving `worker.run_forever` for a few
iterations with a fake registry handler (success, transient failure →
retry, exhausted retries → FAILED, cancel-before-claim).
