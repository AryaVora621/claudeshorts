# Sub-project C (dashboard reshape) — pre-brainstorm outline

Status: draft scaffolding only, written 2026-07-12 ahead of a real
brainstorming session (per the design spec's own note that C "needs its
own brainstorming session — open questions include exact stat tile
selection, whether profile switching is a page-level selector or
all-profiles-at-once layout, and how alerting/notification surfaces
analytics-driven signals vs. just job failures"). This file exists so the
next session doesn't start from a blank page; treat every item below as a
proposal to interrogate, not a decision already made.

Source: `docs/superpowers/specs/2026-07-11-multi-profile-platform-reshape-design.md`
lines 182-195 (Sub-project C's original high-level scope).

## What sub-project A already gives C to build on

- `profiles` table with `id`, `slug`, `display_name`, `active`,
  `auto_publish` — `store/profiles.py` has the CRUD.
- Every `items`/`posts`/`threads`/`runs`/`schedules` row now carries
  `profile_id`.
- Scheduler seeds independent `full_run:<slug>` /
  `drain_scheduled_posts:<slug>` / `weekly_report:<slug>` schedules per
  active profile — job history in `jobs` is filterable by profile via the
  schedule payload, but jobs themselves may not carry `profile_id`
  directly yet (verify before assuming).
- **Not yet done, needed for C**: `claudeshorts/api/*` routes and
  `claudeshorts/dashboard/` templates/routes have zero profile filtering —
  every list/detail endpoint currently returns all profiles' rows mixed
  together. This is C's first real prerequisite, not a nice-to-have.

## Proposed shape (from the spec, needs validation)

1. **New default landing view**: an analytics-forward "monitoring" home,
   replacing today's operator-console Overview page. Per-profile and
   cross-profile stat tiles/trends, headless automation status, job
   health.
2. **Existing pages stay**: Review / Posts / Articles / Schedule /
   Threads / Runs / Jobs / Settings all keep their current function but
   gain a profile filter/selector.
3. **Review queue becomes profile-conditional**: profiles with
   `auto_publish=false` show pending reviews prominently (today's
   behavior); profiles with `auto_publish=true` show recent
   auto-published activity instead, since there's nothing to review.
4. **Telegram bot ties into alerting** — open question: does the bot
   start surfacing analytics-driven signals (e.g. "video underperforming
   retention benchmark") or does it stay job-failure-only until real
   analytics data exists (sub-project B)?

## Open questions to resolve in the actual brainstorming session

- **Profile switching UX**: single active-profile selector (like a
  workspace switcher) vs. an all-profiles-at-once comparison layout on
  the monitoring home? These have very different data-fetching and
  routing implications (query param vs. session state vs. separate
  routes).
- **Stat tile selection**: sub-project A has no real analytics yet
  (that's B) — so what can the monitoring home actually show today?
  Candidates that need zero new data collection: posts published this
  week per profile, pipeline job success/failure rate, time-since-last-run
  per profile, pending review queue depth per profile. Anything beyond
  that (retention, views, engagement) is blocked on B.
- **Does C ship before or after B?** The spec's stat-tile ambition
  ("per-profile and cross-profile stat tiles/trends") implies real
  analytics, but B is unstarted and scoped as its own project needing
  browser-scraping + vidIQ MCP work. Likely sequencing: ship C's
  navigation/filtering/layout shell first with job-health-only tiles,
  then backfill real analytics tiles once B lands — but this should be an
  explicit decision, not an assumption.
- **API profile filtering scope**: does every existing `/api/v1/*` route
  gain a `profile_id` query param, or does the API introduce a
  profile-scoped path prefix (`/api/v1/profiles/<slug>/...`)? Affects the
  dashboard's fetch layer and any external API consumers.
- **Jobs/runs profile attribution**: confirm whether `jobs`/`runs` rows
  reliably carry `profile_id` end-to-end (seed payloads do; worth
  re-checking `jobs/registry.py` and `jobs/worker.py` actually persist it
  onto the row, not just the payload) before building job-health tiles
  that filter by profile.

## Suggested next-session first step

Run an actual `superpowers:brainstorming` session scoped to this file's
open questions before writing a real implementation plan — do not skip
straight to `writing-plans` for sub-project C without it, since the spec
explicitly flagged this as needing its own brainstorm.
