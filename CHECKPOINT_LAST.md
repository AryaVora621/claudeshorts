# CHECKPOINT / RESUME REPORT — 2026-07-12 (session 3: B spec + implementation plan done, ready for parallel subagent execution)

## Session 3 update (read this first, supersedes everything below it)

- **Sub-project B spec approved and committed**:
  `docs/superpowers/specs/2026-07-12-analytics-collection-design.md` (`449f65c`).
- **Sub-project B implementation plan written and committed**:
  `docs/superpowers/plans/2026-07-12-analytics-collection-youtube.md` (`85b3482`).
  8 tasks: (1) `analytics_snapshots` schema + conftest updates, (2)
  `store/analytics.py` CRUD, (3) `rebrowser-playwright` dep + `browser/session.py`,
  (4) YouTube metric extraction, (5) scrape orchestration w/ session-expiry
  + escalation alerting, (6) job registry wiring, (7) scheduler seeding,
  (8) manual live verification.
- **User chose execution approach: Subagent-Driven, parallel.** Not yet
  started. Full dependency graph and exact next steps are in
  `NEXT_SESSION_PROMPT.md` — read that file, it's the authoritative resume
  prompt for session 4. Short version: Task 1 alone first, then Tasks
  2/3/4 in parallel, then 5, then 6, then 7, then 8 (manual, last).
- Nothing else changed this session — sub-project A still closed,
  sub-project C still paused until B ships.

## Session 2 update part 2 (superseded by session 3 above; kept for history)

- **Sequencing decision (user, explicit): sub-project B ships before C.**
  User wants C's dashboard to show real revenue/views/retention/platform
  charts from their reference mockup — not placeholders — so B (real
  analytics collection) has to exist first. C's profile-switcher-UX
  question was already decided (Option A, single active-profile switcher)
  and stays decided; C's stat-tile/auto_publish-tile questions are
  answered too (hide review tile for auto_publish=true, no substitute) but
  moot until B lands. **C brainstorming is paused, not resumed until B is
  done.**
- **B brainstorming just started.** Asked 3 scoping questions together
  (platform order, scrape frequency, storage shape) — **no response after
  600s, unanswered.** My recommendations, offered but not confirmed:
  YouTube first (most stable scrape target + vidIQ MCP bonus source),
  daily scrape tied into the existing per-profile scheduler pattern from
  sub-project A, new dedicated `analytics_snapshots` table (profile_id +
  platform + captured_at) rather than extending `runs`.
- `TASK_QUEUE.md` updated with the B-before-C sequencing decision.

## Next action, in order (session 3)

1. Re-ask (or confirm silently-elapsed recommendation on) B's 3 scoping
   questions: platform rollout order, scrape frequency, storage shape.
2. Continue `superpowers:brainstorming` for sub-project B using its spec
   paragraph (`docs/superpowers/specs/2026-07-11-multi-profile-platform-reshape-design.md`
   lines 165-180) — remaining open question not yet asked: how login-
   session expiry gets surfaced to the operator (Telegram bot alert? dash
   banner?).
3. Once B's design settled and approved, write spec to
   `docs/superpowers/specs/`, spec self-review, user sign-off, then
   `superpowers:writing-plans` — do not skip straight to implementation.
4. Only after B ships: resume sub-project C brainstorming from where it
   left off (session 2's earlier notes below) — profile-switcher UX and
   auto_publish-tile decisions carry forward, stat tile list gets
   reopened now that real analytics data exists.
5. Visual companion server running (project-dir-based) — reuse via
   `start-server.sh --project-dir` (same port) only for genuinely visual
   questions (mockups/layouts), per saved feedback
   (`feedback_visualizer_usage.md`) — not for simple text A/B choices.

---

# Session 2 (part 1) notes below — A closed, "only midnight-curiosity" resolved, C brainstorming (now paused)

## Session 2 update (read this first)

- **Sub-project A: formally CLOSED.** Whole-branch review dispatched and
  passed, verdict "safe to formally mark closed." Two non-blocking
  follow-ups logged in `TASK_QUEUE.md`: (1) `jobs` rows carry `profile_id`
  only inside `payload` JSONB, not as a real column
  (`jobs/registry.py:32-34`) — matters for C's job-health tiles; (2)
  `tests/*/conftest.py` has 8 duplicated `_clean_tables` fixtures that
  truncate the shared `profiles` table with nothing reseeding after.
- **"Only see midnight-curiosity" — resolved, not a bug.** User was
  looking at `http://localhost:8000/` (dashboard root/Overview). Confirmed
  via code read: `claudeshorts/dashboard/app.py`'s `overview` handler has
  **zero profile filtering** today — no switcher, no `profile_id` anywhere
  in that route or its templates. What the user saw was just the Overview
  page's unfiltered recent items/posts/jobs happening to be dominated by
  `midnight-curiosity` activity, with no UI to prove `fork-ai` data exists
  too. This is exactly what sub-project C is for — no separate fix needed.
- **Sub-project C brainstorming in progress**, using the
  `superpowers:brainstorming` visual companion (HTML mockup server) for
  genuinely visual questions only — **user feedback: don't push simple
  A/B text choices to the visualizer**, saved to memory
  (`feedback_visualizer_usage.md`).
  - Q1 (terminal, simple A/B): profile-switching UX — **user picked
    Option A: single active-profile switcher** (workspace-picker style,
    one profile in view at a time, `profile_id` via cookie/query param).
    Decided, not open anymore.
  - User then shared a reference mockup image (Gemini-generated) showing
    desired full dashboard look: top-left profile selector dropdown,
    4-tile KPI row (revenue/views/subscribers/watch time), trend chart,
    platform breakdown donut + revenue bar chart, retention line charts
    per platform, top-performing-content table, audience demographics
    chart. This is the target visual direction for C's eventual full
    build.
  - **Problem flagged, not yet resolved**: almost every metric in that
    mockup (revenue, views, retention, platform breakdown, demographics,
    top content) requires real analytics data that sub-project B hasn't
    built yet. Only real data today is operational: post counts, job
    success/failure, queue depth, time-since-last-run.
  - **Asked user (no response after 600s, timed out)**: should C ship the
    *full* mockup layout now with analytics tiles as placeholder/zero-state
    (wired live once B lands), or ship a *scoped-down* layout with only
    real data today and redesign toward the full mockup once B ships?
    My recommendation is the placeholder-tiles approach (ships the
    polished look immediately, single layout to build once). **Still
    unconfirmed — ask again next session before writing the design doc.**

## Next action, in order (session 3)

1. Ask the interim-data-gap question above (placeholder tiles vs.
   scoped-down layout) — don't guess further, it directly shapes the
   design doc's component list.
2. Continue `superpowers:brainstorming` for sub-project C: work through
   remaining open questions (API profile-filtering shape —
   query-param vs. path-prefix; jobs/runs `profile_id` real-column
   backfill, given the follow-up flagged above; stat tile selection scoped
   to real-data-only per whichever answer to Q above).
3. Once design settled and approved, write spec to
   `docs/superpowers/specs/`, do spec self-review, get user sign-off, then
   invoke `superpowers:writing-plans` — do not skip straight to
   implementation.
4. Sub-project B (real analytics collection) still has no outline — needs
   its own `superpowers:brainstorming` session, not started.
5. Visual companion server is running (project-dir-based, persists in
   `.superpowers/brainstorm/`) — reuse via `start-server.sh
   --project-dir` (same port) if a genuinely visual question comes up
   again; do not restart for simple text choices.

---

## Where things stand (session 1, superseded above where noted)

**Sub-project A (multi-profile data model) is functionally done.** All 8
tasks across 4 waves are merged to `main` (no feature branch — direct to
main was explicitly approved for this work):

- `9ac09e8` Task 5 — one-time migration/backfill script
- `e62913e` Task 6 — profile-scope ingest/select/generate services
- `860d922` Task 7 — auto_publish headless mechanism
- `d56c855` Task 8 — scheduler seeds per-profile schedules
- `a9f14bb` — follow-up fix from Task 8's review (softened an overclaiming
  docstring in `tests/scheduling/conftest.py` about TRUNCATE deadlocks)

Task 8's own review (spec ✅, quality Approved) is the last per-task review
in the plan. **Still pending before sub-project A can be marked fully
closed: the final whole-branch review** (broad review of the full Tasks
1-8 diff, per `superpowers:subagent-driven-development`'s process — not
yet dispatched).

## Full suite status

A `pytest tests/ -v` run was in progress as of this checkpoint (started
11:12AM, background task, ~2400s perl-alarm cap) — **check its result
before doing anything else**, it will tell you whether the DB reseed
below actually fixed things. Prior local runs by the user showed
`ForeignKeyViolation: ... profile_id=1 ... not present in table
"profiles"` across `tests/api/test_articles_api.py` — root cause found
and fixed (see next section). This is NOT one of the 17 known/expected
`profile_id`-fixture-signature failures documented in the plan's Self-
review — it was a different, real environment issue.

## Incident: shared dev/test DB's `profiles` table went empty

The Task 8 implementer agent flagged this risk during its own work and it
materialized: running `tests/scheduling/` (whose `_clean_tables` fixture
now truncates `profiles` too, since Task 8 made `profiles` cascade into
it) against the shared remote Supabase dev DB left the `profiles` table
empty after the test session ended, because nothing reseeds it
afterward. Any other test directory (or manual dashboard/CLI use) that
assumes a persistent `profile_id=1` row exists then breaks with
`ForeignKeyViolation`.

**Fixed this session** by running `scripts/migrate_profiles_backfill.py`'s
`backfill_profiles()` directly against the live DB:
```
fork-ai              -> id 1, active=true
midnight-curiosity   -> id 2, active=true
```
Confirmed via `SELECT id, slug FROM profiles` before/after. **This is a
real fragility, not just a one-time annoyance** — every time
`tests/scheduling/` runs standalone against the shared DB, it will empty
`profiles` again until something reseeds it. Worth a follow-up: either
(a) `tests/scheduling/conftest.py`'s fixture reseeds a baseline profile
after truncating, or (b) tests move off the shared remote DB entirely for
this kind of fixture (out of scope to fix right now, flagging for
awareness).

## Unresolved: user reported "I only see the midnight-curiosity profile"

Investigated but did NOT find the cause before context ran out:
- `claudeshorts/browser/profiles.list_profiles()` (filesystem-based, reads
  `config/profiles/*/profile.yaml`) correctly returns **both** `fork-ai`
  and `midnight-curiosity` when called directly — verified via a one-off
  script.
- `claudeshorts/api/profiles.py`'s `/profiles` route calls that same
  function directly with no filtering — should also return both.
- Did not check: the dashboard's actual rendered Settings/profile page
  (`claudeshorts/dashboard/`), and did not get clarification from the user
  on exactly *where* they only saw one profile (which page/command).
- **Next session: ask the user exactly what they were looking at** before
  guessing further — don't re-derive this from scratch, ask first.

## Sub-project C: pre-brainstorm outline written, no plan yet

Per the user's request to "plan out the full dashboard," wrote
`docs/superpowers/plans/2026-07-12-dashboard-reshape-outline.md` — this
is **scaffolding for a brainstorming session, not a plan**. It captures:
what sub-project A already gives C to build on (profile_id everywhere,
but zero profile filtering yet in `api/`/`dashboard/`), the spec's
original high-level shape (monitoring home, profile-conditional review
queue, Telegram alerting tie-in), and 5 open questions that need a real
`superpowers:brainstorming` session to resolve (profile-switching UX,
what stat tiles are even possible before sub-project B's real analytics
lands, C-before-B sequencing, API filtering shape, jobs/runs profile
attribution).

**Sub-project B (real analytics collection) has no outline yet** — only
the spec's original high-level paragraph exists
(`docs/superpowers/specs/2026-07-11-multi-profile-platform-reshape-design.md`
lines 165-180). Not started this session.

## Next action, in order

1. Check the full-suite pytest run's actual result (background task from
   this session, or just re-run `pytest tests/ -v` fresh — expect 233
   passed / 17 known pre-existing failures, 0 new, now that `profiles` is
   reseeded).
2. Ask the user what exactly showed "only midnight-curiosity" before
   investigating further.
3. Dispatch the final whole-branch review for sub-project A (most capable
   available model, full Tasks 1-8 diff since `merge-base main HEAD` at
   the start of this work) — this is the one remaining gate before
   sub-project A is formally closed.
4. Once user decides whether B or C goes first (or both in parallel): run
   an actual `superpowers:brainstorming` session for whichever is chosen,
   using the relevant outline/spec section as a starting point — do not
   skip straight to `writing-plans`.
5. Update `TASK_QUEUE.md` to reflect whatever gets picked up.
