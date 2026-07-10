# Chunk 3: Service layer extraction

## Context

Third of 14 chunks rebuilding claudeshorts per `goal.md` (see `TASK_QUEUE.md`
/ session task list for the full order). goal.md requires that "the backend
must never depend on the existence of any frontend" and "if multiple
interfaces require the same functionality, expose it through a shared
service" — never duplicating business logic across CLI, dashboard, future
REST API (chunk 4), and Telegram bot (chunk 12).

## Current state

Contrary to what a from-scratch reading of goal.md might suggest,
claudeshorts' CLI (`claudeshorts/cli.py`) is already thin — it imports and
calls domain-package functions (`ingest.run_ingest`, `generate.run_generate`,
`render.render_post`, `orchestrate.run_pipeline`) rather than embedding logic
itself. The actual duplication risk is in `claudeshorts/dashboard/app.py`,
where several route handlers inline real business logic directly:

- `POST /posts/{id}/approve` — set status to `approved`; if not scheduled,
  export immediately.
- `POST /posts/{id}/export` and `POST /posts/{id}/publish-now` — **byte-for-
  byte identical logic**: set status to `approved`, then `export_post`. Two
  routes, one behavior, copy-pasted.
- `POST /posts/{id}/reject` — set status to `rejected` with an optional note.
- `POST /posts/{id}/schedule` — set/clear `scheduled_for`.
- `POST /articles/add`, `POST /articles/{id}/generate`, `POST
  /articles/{id}/pin`, `POST /articles/{id}/unpin` — manual-article
  ingestion, pin/unpin, and job-enqueue-for-generation logic inline.

Chunk 2 (job queue) already introduced `claudeshorts/jobs/registry.py`,
which wraps `run_pipeline`, `run_ingest`, `run_generate`,
`generate_for_item`, and a `_render_post_by_id` helper — these wrapper
functions are effectively proto-services, just private to the `jobs`
package rather than a real, reusable, documented layer.

Settings-related handlers (`/settings/api-key`, `/settings/backend`,
`/settings/general`) already delegate to `claudeshorts/dashboard/auth.py`
and a `settings_io` module — these already function as services and are
**not** touched by this chunk.

## Decision (confirmed with user)

Extract a `claudeshorts/services/` package:

- **`posts_service.py`** — `approve_post`, `reject_post`, `schedule_post`,
  `export_post_now`. `export_post_now` is the single implementation for what
  are today two duplicate code paths (`/posts/{id}/export` and
  `/posts/{id}/publish-now`).
- **`articles_service.py`** — `add_manual_article` (insert + pin-or-enqueue-
  generate branching from `POST /articles/add`), `pin_article`,
  `unpin_article`, `generate_from_item` (enqueues the existing
  `generate_from_item` job type from chunk 2 — this service function is
  what both `/articles/add` (action=generate) and
  `/articles/{id}/generate` call, instead of each building its own job name
  string and closure).
- **`pipeline_service.py`** — `run_ingest_service`, `run_generate_service`,
  `render_post_service`, `run_full_pipeline_service`. These replace the
  private wrapper functions in `jobs/registry.py` — the registry becomes a
  thin `job_type -> services.*` lookup table with no logic of its own.

CLI commands and dashboard route handlers become thin: parse
request/arguments, call a service function, format the response (HTML
redirect vs. `typer.echo`). No business logic — status transitions,
branching on `scheduled_for`, dedup checks — lives in a route handler or CLI
command body after this chunk.

## Architecture

### Why `services/` and not folding this into existing domain packages

`ingest/`, `generate/`, `render/`, `publish/`, `orchestrate/` already contain
the actual domain logic (fetching, prompting Claude, invoking the Node
renderer, exporting to `publish/<platform>/`). Those stay as-is — chunk 3
does not touch them. `services/` sits one level above: it's the
orchestration/coordination layer that combines a domain call with the store
status-transition side effects a UI action implies (e.g. "approve" = a
`store.set_status` call + conditionally calling `publish.export_post`, which
is coordination, not domain logic itself). This mirrors goal.md's own
example service chain (Generation → Scheduling → Publishing → Storage) —
`services/` is where those steps get composed for a given user-facing
action, without domain packages needing to know about each other.

### Return shapes

Every service function returns a plain dict or raises a domain exception
(`ValueError` for "not found", `FileNotFoundError` for missing render
output — both already used today) — never an HTTP response or Typer echo.
Callers (CLI, dashboard, later REST API/Telegram) are responsible for
turning that into their own presentation:

```python
approve_post(post_id: int) -> dict
# {"post_id": int, "exported": bool, "scheduled_for": str | None}
# raises ValueError if post_id doesn't exist

export_post_now(post_id: int) -> dict
# {"post_id": int}
# raises ValueError (not found) or FileNotFoundError (missing render output)
```

### `jobs/registry.py` after this chunk

```python
JOB_HANDLERS = {
    "full_run": lambda payload: pipeline_service.run_full_pipeline_service(force=True),
    "ingest": lambda payload: pipeline_service.run_ingest_service(),
    "generate": lambda payload: pipeline_service.run_generate_service(),
    "generate_from_item": lambda payload: pipeline_service.render... # see plan
    "render_post": lambda payload: pipeline_service.render_post_service(payload["post_id"]),
}
```

(Exact lambdas finalized in the plan — the point locked in here is that
`registry.py` contains zero inline pipeline-calling logic after this chunk,
only a lookup table pointing at `services/`.)

## Out of scope for this chunk

- REST API (chunk 4) — `services/` is built so chunk 4 can expose each
  function as an endpoint with near-zero glue, but no endpoints are added
  here.
- Settings handlers — already service-shaped via `auth.py`/`settings_io`,
  left untouched.
- Any new business logic or behavior change — this is a pure extraction;
  approve/reject/export/schedule/pin/unpin behave identically to today,
  including the `/posts/{id}/export` vs `/posts/{id}/publish-now`
  duplication being collapsed into one function (behavior identical, code
  path unified).

## Testing

`tests/services/test_posts_service.py`, `test_articles_service.py`,
`test_pipeline_service.py` — each service function tested directly against
the Supabase test project (same pattern as chunks 1-2), plus updated
`tests/dashboard/` tests confirming route handlers still produce the same
HTTP redirects/messages after delegating to services.
