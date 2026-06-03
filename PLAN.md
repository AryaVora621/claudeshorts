# PLAN — Live jobs dashboard (frontend + progress instrumentation)

Goal: live-updating dashboard with percent bars, the ability to click back onto
any job you have run (surviving restarts) and watch its terminal from inside the
dashboard.

Agent: Claude (Opus 4.8), branch `feature/carousel-wider-topics`.

## Decisions (confirmed with user)
- Add minimal read-only progress plumbing (a core `progress` module).
- Persist jobs to SQLite so history survives restarts.
- Full daily run shows BOTH a phase bar (ingest, generate, render, publish) AND
  a per-item bar (post M of N, frame M of N).
- Backend step-count instrumentation is sanctioned for ingest and render.
- The terminal view is embedded in the dashboard (the `/jobs` page), not a bare
  page. No stop/cancel. No change to what jobs actually do.

## Progress model (two levels)
- phase: index / total + label   (e.g. "generate", 2 of 4)
- step:  current / total + label (e.g. post 3 of 12, or frame 40 of 900)
- step.total == 0 means indeterminate (animated bar).

Delivery: core `claudeshorts/progress.py` holds a per-thread sink. Pipeline code
calls `progress.phase(...)` / `progress.step(...)`; the dashboard installs a sink
on each job's worker thread. Core never imports the dashboard (clean layering),
and the calls are harmless no-ops when no sink is set.

## Steps
Core/progress:
1. `claudeshorts/progress.py` — thread-local sink, `phase()`, `step()`, set/clear.
2. `ingest/runner.py` — per-feed `step(i, N, name)`.
3. `generate/runner.py` — per-post `step(idx, total, title)`.
4. `orchestrate/runner.py` — 4 `phase()` calls + per-item steps in render/publish.
5. `renderer/render.mjs` — emit `PROGRESS f/total` to stderr per frame.
6. `render/bridge.py` — stream stderr via Popen, parse PROGRESS -> `step()`.
7. `publish/exporter.py` — per-post step in `publish_due_posts`.

Persistence:
8. `store/db.py` — add `jobs` table to SCHEMA (additive).
9. `store/jobs.py` — new data-access module (mirror `runs.py`).
10. `store/__init__.py` — export the helpers.

Dashboard runtime:
11. `dashboard/jobs.py` — Job gains phase/step fields; install progress sink per
    worker thread; insert on start, throttled persist, full log + status on
    finish; lazy `_ensure_init()` seeds id counter from DB and marks orphaned
    `running` rows `interrupted`; `get_job`/`recent_jobs` fall back to DB.

Routes + UI:
12. `dashboard/app.py` — `GET /jobs` (list), `GET /jobs.json` (snapshot), extend
    the SSE stream to also emit `progress` events.
13. `templates/base.html` — add "Jobs" to the nav.
14. `templates/jobs.html` — NEW: live list (cards + bars) + embedded terminal pane.
15. `templates/job.html` — dual progress bars above the live terminal.
16. `templates/overview.html` — live recent-jobs widget with bars + link.
17. `static/jobs.js` — NEW: shared poll/render + terminal attach (live or stored).
18. `static/app.css` — progress bar component + polish.

## Verify
- `python -m claudeshorts.cli init-db` creates the jobs table.
- Import smoke test of progress + instrumented modules.
- Start `serve`, run generate, confirm bars + live terminal + persistence after
  a restart (interrupted state for anything mid-flight).
