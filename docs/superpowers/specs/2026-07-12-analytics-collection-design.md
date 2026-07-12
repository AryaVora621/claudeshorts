# Sub-project B: real analytics collection — design spec

Status: approved design, ready for `superpowers:writing-plans`.

Source: `docs/superpowers/specs/2026-07-11-multi-profile-platform-reshape-design.md`
lines 165-180 (sub-project B's original high-level scope), refined via a
`superpowers:brainstorming` session on 2026-07-12.

## Why this exists

`reporting_service.weekly_report` currently hardcodes
`platform_engagement: {"status": "pending"}` — there is no real
cross-platform analytics data anywhere in claudeshorts today. Sub-project C
(dashboard reshape) is blocked on this: the user wants C's monitoring home
to show real revenue/views/retention/platform-breakdown charts, not
placeholders, so this data has to exist first. Decided sequencing:
**B ships before C.**

## Scope: Phase 1 is YouTube only

Three platforms are in the long-term scope (YouTube, Instagram, TikTok) but
this spec covers **Phase 1: YouTube Studio only**. Reasoning: YouTube
Studio is the most stable/documented scrape target, and the vidIQ MCP
server gives a bonus supplementary data source for YouTube specifically.
Instagram Professional Dashboard and TikTok Analytics are explicit
follow-up phases once this phase's scraping pattern is proven — each gets
its own spec/plan when picked up, reusing the architecture below.

## Architecture

A new `analytics_service` module in the existing services layer
(`claudeshorts/services/analytics_service.py`), following the same
services-layer convention as every other pipeline stage — thin callers
(CLI, dashboard, API, job registry) call into it, business logic lives
here.

**Job integration**: a new job type, `scrape_analytics:<slug>`, registered
in `jobs/registry.py` — same pattern as sub-project A's
`full_run:<slug>` / `drain_scheduled_posts:<slug>` / `weekly_report:<slug>`.
The scheduler (`scheduling/`) seeds one `scrape_analytics:<slug>` schedule
per active profile, running **daily**, matching the existing per-profile
scheduling pattern rather than introducing a new cadence concept.

**Scraping mechanism**: `rebrowser-playwright` (not plain Playwright — the
spec calls this out explicitly for scrape-detection resistance, since this
is the one place in the codebase that scrapes an authenticated third-party
UI, as opposed to the RSS/public-page fetching `ingest/` already does).
Drives a logged-in browser session using the per-profile session storage
already built in sub-project A's `browser/profiles.py` and
`config/profiles/<slug>/profile.yaml` — no new session/login-management
system needed, this reuses what exists.

Navigates to YouTube Studio's Analytics tab and extracts:
- **Primary (retention/conversion metrics, prioritized per the deep-research
  finding that vanity metrics are too noisy at low sample sizes to act
  on)**: average view duration, 7-second retention.
- **Secondary (vanity metrics, still useful for the dashboard's KPI tiles)**:
  views, subscriber count/delta.

vidIQ MCP is wired in as a **bonus supplementary source** for the same
profile's YouTube data where available — additive, not a dependency; if
vidIQ is unavailable for a profile, the direct YouTube Studio scrape alone
is still sufficient.

## Data storage: new `analytics_snapshots` table

A new table, not an extension of `runs` (runs is about pipeline execution,
analytics is about content performance — different concerns, and mixing
them would make both harder to query).

```
analytics_snapshots
  id            serial primary key
  profile_id    int references profiles(id)
  platform      text            -- 'youtube' for Phase 1; enum-like, more values added in later phases
  captured_at   timestamptz
  metrics       jsonb           -- {"avg_view_duration_sec": ..., "retention_7s_pct": ..., "views": ..., "subscribers": ...}
```

`metrics` is JSONB rather than fixed columns because the metric set will
grow when Instagram/TikTok phases add platform-specific fields (e.g.
Instagram doesn't have "7-second retention" as a concept) — a fixed-column
schema would need a migration per platform added. One row per scrape run
(daily), so the table is naturally a time series queryable by
`profile_id` + `platform` + `captured_at` range — this is what feeds C's
eventual trend charts.

## Error handling and alerting

Scrape failures are distinguished into two classes:

1. **Session expired / login invalid** (auth failure specifically) — this
   needs a human to re-log-in via the browser profile, it won't self-heal
   on retry. Triggers **both**:
   - A Telegram push notification immediately, via the existing
     `notify.py` pattern already wired for job failures (same mechanism,
     new message type).
   - A persistent dashboard banner/indicator that stays up until a
     subsequent scrape for that profile succeeds again (i.e. it's a
     state, not a one-time toast — check on every scrape attempt whether
     the banner should clear).
2. **Transient scrape error** (selector changed, page timeout, network
   blip) — logged, no alert. The next day's scheduled run retries
   naturally; only escalate to an alert if failures persist across N
   consecutive days (exact N is an implementation-plan detail, not a
   design decision — default to 3 unless the plan finds a reason
   otherwise).

## Testing

- **Unit tests**: mock the Playwright page/session object to test the
  metric-extraction/parsing logic in isolation — this is the part most
  likely to break when YouTube Studio's UI changes, and the part cheapest
  to test without a real browser.
- **Live verification**: before calling Phase 1 done, run the scraper
  against a real logged-in YouTube Studio session for at least one profile
  and confirm the extracted metrics match what's visible in the UI by eye
  — same manual-verification bar sub-project A used for its own
  live-data checks.
- Do **not** attempt to unit-test against a live scrape in CI — third-party
  UI scraping is inherently environment-dependent (login state, YouTube UI
  changes); keep CI tests to the mocked parsing layer only.

## Explicitly out of scope for this spec

- Instagram and TikTok scraping (follow-up phases, own specs later).
- Sub-project C's dashboard consumption of this data (separate
  sub-project, resumes once this ships — its profile-switcher UX and
  auto_publish-tile-visibility questions are already decided from an
  earlier brainstorming session and carry forward unchanged).
- Weekly/monthly rollup or aggregation views over `analytics_snapshots`
  (C or a later B follow-up can add these once there's more than a few
  days of real data to aggregate).
- Retry/backoff tuning specifics (the "3 consecutive days" escalation
  threshold above is a placeholder default, not a firm requirement — the
  implementation plan can adjust it).
