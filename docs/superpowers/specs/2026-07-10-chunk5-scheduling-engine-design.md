# Chunk 5: Scheduling engine

## Context

Fifth of 14 chunks rebuilding claudeshorts per `goal.md` (see `TASK_QUEUE.md`
/ session task list). goal.md requires publishing to support immediate,
scheduled, recurring, and approval-gated execution, with scheduling logic
living in its own service.

## Current state

Immediate, scheduled, and approval-gated publishing already exist:
`services.posts_service.approve_post` exports immediately unless a post has
a future `scheduled_for` date, and `publish.publish_due_posts(on_date)`
drains the future-posts queue (approved + due) — but it only runs as the
last step of `orchestrate.run_pipeline`, so scheduled posts only actually
publish when a human (or external OS cron) triggers the full daily run.
There is no **recurring** mechanism inside the app itself — claudeshorts
has always relied on an operator or the host OS's cron/launchd to invoke
`claudeshorts run` on a schedule.

## Decisions (confirmed with user)

1. **Add a self-contained recurring scheduler**, independent of external
   cron/launchd, so the Raspberry Pi deployment needs nothing beyond
   running the claudeshorts process itself (goal.md: "design for continuous
   operation"). Two default recurring schedules ship with this chunk:
   - Daily full pipeline run (`full_run` job type) at a configurable
     time-of-day.
   - Hourly scheduled-posts drain (new `drain_scheduled_posts` job type,
     wrapping the existing `publish_due_posts`) so a post's `scheduled_for`
     date is honored within about an hour instead of waiting for the next
     full daily run.
   No cron-expression parsing library is added — schedules are expressed as
   either "daily at HH:MM" or "every N hours/minutes", which covers both
   defaults and is simpler to reason about than general cron syntax for a
   single-operator tool.
2. **Weekly performance report — internal metrics only in this chunk.**
   Real cross-platform engagement (views/likes/follows) requires either
   platform APIs or, per the user's explicit choice, **Playwright-based
   scraping of each platform's logged-in analytics/studio pages** — both
   routes need real browser profiles/logins, which is chunk 11 (deferred,
   human-required). This chunk's weekly report covers what's derivable from
   existing tables today: posts generated/approved/rejected/exported this
   week, per-platform export counts, thread/follow-up activity, and
   ingest/generate success/failure rates — with an explicit "platform
   engagement: pending Playwright analytics (chunk 11)" placeholder section
   so the report's shape doesn't need to change when that data arrives.
   Chunk 11's task description has been updated to include building the
   Playwright analytics scraper using the same browser-profile objects it
   already builds for publishing.

## Architecture

### New `schedules` table (Postgres, additive)

```sql
CREATE TABLE IF NOT EXISTS schedules (
    id           BIGSERIAL PRIMARY KEY,
    name         TEXT        NOT NULL UNIQUE,
    job_type     TEXT        NOT NULL,
    payload      JSONB       NOT NULL DEFAULT '{}'::jsonb,
    kind         TEXT        NOT NULL,        -- 'daily_at' | 'every_minutes'
    daily_at     TEXT,                        -- 'HH:MM', used when kind='daily_at'
    every_minutes INTEGER,                    -- used when kind='every_minutes'
    enabled      BOOLEAN     NOT NULL DEFAULT true,
    next_run_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_run_job_id BIGINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `claudeshorts/scheduling/` package (new)

- `store.py` — thin data access (`list_schedules`, `get_schedule`,
  `upsert_schedule`, `mark_ran`), following the same convention as
  `claudeshorts/store/*.py`.
- `compute.py` — `next_run_at(kind, daily_at=None, every_minutes=None, *,
  after=None) -> datetime`, pure function (easy to unit test without a DB
  or real clock — `after` parameter makes "now" injectable).
- `scheduler.py` — polling loop, same style as chunk 2's `jobs/worker.py`:
  every poll interval, find schedules where `enabled` and `next_run_at <=
  now()`, enqueue their `job_type`/`payload` via `jobs.queue.enqueue`,
  recompute and store the next `next_run_at`. Runs as a daemon thread
  started alongside the chunk-2 worker thread at dashboard startup.

Two default schedules are seeded on `init_db()` (or a dedicated
`seed_default_schedules()` called at startup, idempotent via the `name`
unique constraint):
- `"daily-full-run"`: `job_type="full_run"`, `kind="daily_at"`,
  `daily_at` from `config/settings.yaml`'s new `schedule.daily_run_time`
  (default `"08:00"`).
- `"hourly-scheduled-drain"`: `job_type="drain_scheduled_posts"`,
  `kind="every_minutes"`, `every_minutes=60`.

### New job type: `drain_scheduled_posts`

Added to chunk 3's `services/pipeline_service.py`
(`drain_scheduled_posts_service() -> list[int]`, wrapping
`publish.publish_due_posts()`) and chunk 3's `jobs/registry.py`
(`"drain_scheduled_posts": lambda payload:
pipeline_service.drain_scheduled_posts_service()`).

### Weekly report

`services/reporting_service.py` — `weekly_report(as_of: date | None = None)
-> dict`:

```python
{
    "week_start": "2026-07-06", "week_end": "2026-07-12",
    "posts_generated": 12, "posts_approved": 9, "posts_rejected": 2,
    "posts_exported": 9,
    "exports_by_platform": {"youtube": 9, "tiktok": 9, "instagram": 9},
    "threads_active": 4, "follow_ups": 3,
    "ingest_runs": {"ok": 7, "error": 0},
    "generate_success_rate": 0.92,
    "platform_engagement": {
        "status": "pending",
        "note": "Requires Playwright-based analytics scraping via logged-in "
                "browser profiles — see chunk 11.",
    },
}
```

A third default schedule, `"weekly-report"`
(`job_type="weekly_report"`, `kind="daily_at"`, runs once a week — since
`kind` only supports daily/interval, weekly is modeled as `daily_at` plus a
day-of-week check inside `compute.next_run_at`, e.g. only advancing
`next_run_at` to the next Monday — this keeps the `kind` vocabulary from
growing a third value just for one schedule). The job's result (the dict
above) is logged to the job's `log` column (same mechanism every other job
already uses) and, in a later chunk, could be delivered via Telegram
(chunk 12) — this chunk only produces and persists the report, it does not
add a delivery channel.

## Out of scope for this chunk

- Cron-expression parsing (deliberately simplified to daily-at/every-N-
  minutes).
- Real cross-platform engagement metrics (chunk 11, deferred — needs
  Playwright + logged-in browser profiles).
- Any UI for managing schedules (dashboard/API CRUD over the `schedules`
  table) — the two/three default schedules are enough for this chunk;
  exposing schedule management as its own dashboard page or API routes is
  straightforward future work once there's a concrete need to add/edit
  schedules beyond the defaults.

## Testing

`tests/scheduling/test_compute.py` (pure function, no DB), `test_store.py`,
`test_scheduler.py` (polling loop against the live Supabase project,
matching chunks 1-4's pattern), `tests/services/test_reporting_service.py`.
