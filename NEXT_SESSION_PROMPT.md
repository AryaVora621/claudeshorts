# Resume prompt — execute sub-project B implementation plan (parallel, subagent-driven)

Paste this as the first message of the new session.

---

Resume this project. Read `CLAUDE.md`, `CHECKPOINT_LAST.md`, and
`TASK_QUEUE.md` first per standing convention.

**Sub-project A (multi-profile data model): fully closed.** Nothing to do.

**Sub-project B (real analytics collection), Phase 1: YouTube only —
design spec approved and implementation plan written and committed:**
- Spec: `docs/superpowers/specs/2026-07-12-analytics-collection-design.md` (`449f65c`)
- Plan: `docs/superpowers/plans/2026-07-12-analytics-collection-youtube.md` (`85b3482`)

**User has chosen the execution approach: Subagent-Driven, running tasks
in parallel where the plan's dependency graph allows.** Use
`superpowers:subagent-driven-development`. Task dependency graph from the
plan:

- Task 1 (schema: `analytics_snapshots` table + 8 conftest `_TABLES`
  updates) — run first, alone, nothing else can start until it merges.
- Tasks 2 (`store/analytics.py` CRUD), 3 (`rebrowser-playwright` dep +
  `browser/session.py`), 4 (metric extraction in `analytics_service.py`)
  — each depends only on Task 1 (or nothing) — **dispatch these three in
  parallel** once Task 1 is done and reviewed.
- Task 5 (scrape orchestration `scrape_youtube_analytics`) — needs
  2 + 3 + 4 all merged first (it imports from all three).
- Task 6 (job registry wiring) — needs Task 5.
- Task 7 (scheduler seeding) — needs Task 6.
- Task 8 (manual live verification against a real YouTube session) —
  last, after everything else, not subagent-automatable (needs a human
  login step).

Two-stage review between tasks, per the skill. Do not skip the final
whole-branch review once all 8 tasks are done, before marking B closed
(same closing gate sub-project A used).

**Sequencing reminder**: sub-project C (dashboard reshape) stays paused
until B ships — user wants C's dashboard to show real data from B, not
placeholders. C's already-decided sub-answers (single active-profile
switcher UX; auto_publish=true profiles hide the review tile, no
substitute) carry forward unchanged once C resumes — do not re-ask them.

A visual companion (HTML mockup) server may still be idle from earlier —
only use it for genuinely visual layout questions, not simple text
choices (see feedback memory `feedback_visualizer_usage.md`).
