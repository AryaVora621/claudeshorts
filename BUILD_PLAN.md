# BUILD PLAN — fork.ai build-out (resume from here after clearing context)

> Read this file first on a fresh session. Authoritative plan for what to
> execute next. Companion status files: `CHECKPOINT_LAST.md`,
> `TASK_QUEUE.md`, `NEEDS_FROM_YOU.md`. Detailed task specs live in
> `docs/superpowers/plans/2026-07-12-analytics-collection-youtube.md` (B)
> and `docs/superpowers/plans/2026-07-12-dashboard-reshape-outline.md` (C).

## Context (already done, do not redo)
- MVP pipeline (ingest→select→generate→render→review→publish) verified live.
- `goal.md` platform rebuild (chunks 1–9 + 12) merged to `main`: Postgres/
  Supabase store, job queue + worker, `/api/v1` REST API, scheduler, LLM
  abstraction, Telegram bot, brand templates + carousel/end-slide.
- **Sub-project A (multi-profile data model): CLOSED.** Profiles: `fork-ai`
  (id 1), `midnight-curiosity` (id 2).
- Live Supabase configured (`SUPABASE_DB_URL` in `.env`, project
  `nddlutmilajkqtoygmfi`). OpenRouter key set. Telegram bot built (token +
  chat id in `NEEDS_FROM_YOU.md`) but NOT yet started live.

## Resolved — "I only see midnight-curiosity profile"
NOT a bug. Confirmed in code: the dashboard Overview/`overview` route has
**zero profile filtering** today. Expected — sub-project C adds the profile
switcher. Do NOT investigate further; C is the fix. The user confirmed they
saw it on the homepage/dashboard because no profile filter exists yet.

## Decisions locked (this session)
- **Home PC / aiserver (Nvidia P40) is OFFLINE — avoid it.** Use the macOS
  desktop (Node 24, Playwright Chromium, ffmpeg 8.1 all present) for any
  rendering. Pure-Python work needs no rendering.
- **Branding = "fork.ai" v4, LOCKED + generate now.** Flat `#111111` bg,
  purple `#A855F7` accent, `#F5F0FF` text, JetBrains Mono, flat 4-prong fork
  mark. Carry the brand into the renderer before first publish (Phase 1).

## Execution order

### Phase 1 — Branding lock (independent, do FIRST)
1. Copy `Brandkit/fork/logo_1024x1024.png` → `assets/logo.png`
   (settings.yaml `channel.logo` already references `assets/logo.png`; the
   file is currently missing).
2. Generate a fork.ai-branded `assets/EndingSlide.png` via Playwright
   (reuse the brandkit HTML/CSS approach from `Brandkit/fork/*.html`):
   flat `#111111`, purple `#A855F7` fork mark, "fork.ai" wordmark + tagline
   "AI & tech news, forked daily". Replaces the current generic end card.
3. Verify the renderer picks both up (`render/bridge.py::_endslide_path`
   auto-detects `assets/EndingSlide.png`; `channel.logo` drives the outro
   watermark). Render one post headless and eyeball the outro + watermark.

### Phase 2 — Sub-project B (YouTube analytics collection)
- Spec: `docs/superpowers/specs/2026-07-12-analytics-collection-design.md`
- Plan: `docs/superpowers/plans/2026-07-12-analytics-collection-youtube.md`
- **Execution: `superpowers:subagent-driven-development`, parallel.**
  Dependency graph:
  - Task 1 (schema: `analytics_snapshots` + 8 conftest `_TABLES` updates)
    → run FIRST, alone.
  - Tasks 2 (`store/analytics.py`), 3 (`rebrowser-playwright` dep +
    `browser/session.py`), 4 (`_extract_youtube_metrics`) → parallel (each
    only needs Task 1).
  - Task 5 (orchestration `scrape_youtube_analytics`) → needs 2+3+4.
  - Task 6 (job registry wiring) → needs 5.
  - Task 7 (scheduler seeding) → needs 6.
  - Task 8 (MANUAL live verification) → last, gated on user (see below).
- Two-stage review between tasks per the skill. Full suite expectation:
  233 passed / 17 known pre-existing failures / 0 new.
- **Task 8 is NOT automatable** — it needs a real logged-in YouTube Studio
  session. Leave it as a documented manual step.

### Phase 3 — Sub-project C (dashboard reshape)
- Outline: `docs/superpowers/plans/2026-07-12-dashboard-reshape-outline.md`
- **Run `superpowers:brainstorming` first** on remaining open questions
  (stat-tile selection now that B lands, API `profile_id` filtering shape,
  jobs/runs `profile_id` attribution), THEN `writing-plans`, THEN implement.
  Do not skip straight to implementation.
- **Carry-forward decisions (do NOT re-ask):** single active-profile
  switcher UX; `auto_publish=true` profiles hide the review tile (no
  substitute). Build: analytics-forward monitoring home + profile filtering
  across existing pages + analytics tiles fed by B's `analytics_snapshots`.

## What's needed from the user (human-gated)
- **Channel creation (user-owned, not a coding task):** create the `@fork.ai`
  YouTube + Instagram accounts (TikTok handle still unverified — geoblocked,
  check `tiktok.com/@fork.ai` manually). Bio/category/recovery-email steps
  are in `Brandkit/fork/README.md` "What's still needed to actually launch."
- **Before Task 8 of B:** one-time interactive YouTube Studio browser login
  to save `browser/profiles/fork-ai/storage_state.json` (Task 8 Step 1 in the
  B plan). After that, live scrape verification can run.
- **Newsletter platform** (Substack/beehiiv) — future, not started, not
  blocking.
- **Telegram bot live start** — needs explicit go-ahead (built, not running).

## Explicitly OUT OF SCOPE / deferred
Home P40 server + local Qwen3-30B model · Reddit OAuth (sources 403) ·
real API publishing plugins (chunk 10, skipped — folder export only) ·
Higgsfield/Veo video gen (decision: use Google AI Pro subscription) ·
cross-outlet dedup (user: "some duplicates are fine").

## Quick-start command for a fresh session
Paste: "Resume the fork.ai build-out. Read BUILD_PLAN.md first, then
CHECKPOINT_LAST.md and TASK_QUEUE.md. Execute Phase 1 (branding) then Phase 2
(sub-project B, subagent-driven parallel per its plan)."
