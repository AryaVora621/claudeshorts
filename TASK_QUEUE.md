# Task Queue

## Open
- **Multi-profile platform reshape — sub-project A CLOSED (final review passed 2026-07-12), B/C in brainstorming**
  all 8 tasks merged to `main` (see Done section). Final whole-branch
  review dispatched and passed — verdict "safe to formally mark closed",
  no blocking issues. Two non-blocking follow-ups carried forward:
  (1) `jobs` rows don't carry `profile_id` as a real column, only inside
  `jobs.payload` JSONB (`jobs/registry.py:32-34`) — sub-project C's
  job-health dashboard will need either a real column + backfill or
  payload-JSON filtering; (2) `tests/*/conftest.py` has 8 duplicated
  copies of the `_clean_tables` fixture that truncates the shared
  `profiles` table with nothing reseeding it after — recommend dedupe to
  one `tests/conftest.py` + reseed-after-truncate or transactional
  rollback.
  STILL UNRESOLVED: user reported "I only see midnight-curiosity profile"
  but has not yet said where (which page/command) — asked twice this
  session, no response after 600s both times. Do not guess further; ask
  again next session before investigating.
  **SEQUENCING DECIDED (user, session 2): B ships before C.** User wants
  C's dashboard to show real revenue/views/retention/platform-breakdown
  charts (per a reference mockup they shared), not placeholders — so
  sub-project B (real analytics collection) must be built first.
  Sub-project C brainstorming (profile-switcher UX only — user picked
  "single active-profile switcher") is paused, not abandoned; resume once
  B lands. Sub-project C's other open questions (stat tile selection,
  auto_publish=true profiles hide the review tile instead of showing
  substitute activity — user decided this too) will be revisited then.
  **B design spec written and committed**:
  `docs/superpowers/specs/2026-07-12-analytics-collection-design.md`
  (`449f65c`). Phase 1 = YouTube only (Instagram/TikTok later phases).
  **B implementation plan written**:
  `docs/superpowers/plans/2026-07-12-analytics-collection-youtube.md`
  (not yet committed) — 8 tasks: schema, store CRUD, browser session
  helper + rebrowser-playwright dep, metric extraction, scrape
  orchestration w/ session-expiry + escalation alerting, job registry
  wiring, scheduler seeding, live verification. Self-review noted vidIQ
  MCP bonus source is deliberately deferred (not a Phase 1 task). Awaiting
  user's execution-approach choice (subagent-driven vs inline) before any
  implementation starts.
  See `NEXT_SESSION_PROMPT.md` for full resume detail.
- Follow-up (not blocking): `tests/scheduling/conftest.py`'s
  `_clean_tables` fixture truncates the shared `profiles` table and
  nothing reseeds it afterward — every standalone run of
  `tests/scheduling/` against the shared remote DB breaks other test
  directories/manual use until someone reseeds `profiles`. Consider having
  the fixture reseed a baseline profile, or moving off the shared DB for
  this fixture.
- SKIPPED (user decision, `NEEDS_FROM_YOU.md` §2): chunk 10 (real API-key
  publishing plugins for YouTube/TikTok/Instagram) — keeping folder-export
  only for now. Superseded by the reshape's analytics-via-scraping
  decision above for the read side; publishing-side API credentials still
  not wanted.
- goal.md platform rebuild chunks 10/11/13/14 remain unimplemented, each
  gated on a human-provided credential/login (full detail in
  `CHECKPOINT_LAST.md`). Chunks 1-9 + 12 are done (see Done section).
- BLOCKED on hardware: test the branch on the HOME SERVER (aiserver desktop,
  Nvidia P40). Server `192.168.1.178` is currently unreachable (incomplete ARP
  from a same-subnet host) — user is troubleshooting the Linux box (rebooted,
  tried ethernet). Once it is back: pull, ingest, generate --limit 20, render,
  eyeball video + carousel + endslide, then open a PR / merge to main.
- PLANNED: local model generation backend (Qwen3-30B-A3B GGUF on the P40) as a
  free alternative to claude_cli / api. Full plan in `docs/PLAN_local_model.md`.
  Key note: the P40 is Pascal, so fp8 is NOT possible — use integer-quantized
  GGUF (Q4/Q5) via Ollama or llama.cpp. Open decisions listed in the plan.
- DEPRIORITIZED — cross-outlet duplicate stories: "some duplicates are fine"
  (user). Investigation notes in CHECKPOINT_LAST.md (IDF-weighted shared-token
  approach; RTX-Spark false-merge risk). Revisit only if it becomes annoying.
- Optional: parallelize batch generation (run a few claude CLI calls at once).
- Optional: Reddit OAuth so the disabled reddit sources work again.

## In-Progress
- (none — the pre-rebuild "live jobs dashboard" item that used to live here
  was superseded by the goal.md rebuild's job queue + dashboard SSE
  progress streaming, chunks 2/6, both done. See Done section.)

## Done
- **Multi-profile data model — sub-project A** (2026-07-11/12): all 8
  tasks merged to `main` (`9ac09e8`, `e62913e`, `860d922`, `d56c855`,
  `a9f14bb`). Per-task spec+quality reviews all passed. Full suite:
  233 passed, 17 known pre-existing failures (documented non-goal),
  0 new. `profiles` table reseeded (`fork-ai`=1, `midnight-curiosity`=2)
  after a scheduling-test-truncation incident emptied it mid-session.
  Final whole-branch review not yet dispatched — see Open.
- **Chunk 12 — Telegram bot** (2026-07-11): full chunk complete —
  `GET /profiles` + `POST /jobs/{id}/retry` REST endpoints, `ApiClient`
  (thin REST wrapper), command handlers (`/queue /generate /approve
  /reject /retry /profiles /workers /logs`, single-admin-chat gated), and
  push notifications (`notify.py`, wired into the job worker: job failure
  + weekly-report completion). Full 226-test suite confirmed green
  against the real Supabase connection (29m25s) before the final commit.
  Bot not yet started as a live background process — pending explicit
  go-ahead per CHECKPOINT_LAST.md.
- Real Supabase data migration (chunk 1 Task 11): items=616, threads=13,
  posts=13, post_threads=13, runs=3, all verified against the hosted project
  `nddlutmilajkqtoygmfi` via direct MCP `execute_sql`. Full detail in
  CHECKPOINT_LAST.md.
- Live app `.env` `SUPABASE_DB_URL` now points at the real Session Pooler
  connection (user provided password + pooler host 2026-07-11). Verified with
  a direct `psycopg` connection: `items` count 616, `posts` count 13, matching
  the migration. The app no longer needs the local docker Postgres fallback.
- **fork.ai** brand kit (was "Terminal Brief" — renamed after user feedback
  that the neon-glow design read as generic AI-generated aesthetic; now flat,
  no gradients/glow). Logo + YouTube banner + IG highlight cover rendered via
  HTML/CSS + Playwright screenshot, plus bios reflecting the dual video +
  newsletter format. Saved to `Brandkit/fork/` in the project root (renamed
  from `Brandkit/TerminalBrief/`). See `Brandkit/fork/README.md` for the full
  kit, including a "what's still needed to launch" checklist (YouTube/
  Instagram account setup steps, and a newsletter platform — Substack/
  beehiiv/self-hosted — which is not set up yet).
  **Handle: `@fork.ai`** (brand name and handle are now the same). Chosen
  after live browser verification of ~25 candidate handles across Instagram +
  YouTube (see README for the full taken/available list and the naming
  research behind it). TikTok was NOT verified — the browser tool couldn't
  reach TikTok this session (geoblocked per user); check
  `tiktok.com/@fork.ai` manually before creating the account. Account
  creation itself is a user-owned next step.
- goal.md rebuild implementation, chunks 1-8, via subagent-driven
  development on branch `feature/platform-rebuild` — **merged to main**
  (commit 851f2f6). Store fully Postgres; job queue + worker; services/
  layer; REST API at /api/v1; self-contained scheduler; unified
  structured logging; LLM provider abstraction (claude_cli/api/local/
  openai_compat); brand-color pinning + editorial/breaking renderer
  templates. Final whole-branch review (Opus) found and fixed one real
  cross-chunk gap: orphaned RUNNING jobs never recovered after a worker
  crash (mark_running_interrupted existed but was unwired and used stale
  lowercase vocabulary) — now wired into startup via a FastAPI lifespan
  handler, flips orphans to FAILED. 190/190 tests. Progress ledger:
  `.superpowers/sdd/progress.md`. Feature branch deleted (merged, not
  pushed to origin). Remaining: chunk 1 Task 11 (real data migration) and
  chunks 10-14 (publishing plugins, browser profiles, Telegram bot,
  Veo, extra LLM keys) — all human-required, see Open. A
  `NEEDS_FROM_YOU.md` fill-in form is sitting in the repo root collecting
  the needed credentials/decisions for all of these.
- Fixed macOS/kitty launcher minimal-PATH failure: `start-dashboard.sh` now
  prepends standard macOS local install paths and `find_python()` falls back to
  `.venv/bin/python`, Homebrew, `/usr/local/bin`, and python.org framework
  Python paths. Verified `./start-dashboard.sh` and `./start-dashboard.command`
  under `PATH=/usr/bin:/bin:/usr/sbin:/sbin`; both served the dashboard with
  HTTP 200 and were stopped cleanly.
- LAN-accessible dashboard: `start-dashboard.sh` now binds to all interfaces by
  default (override with `CLAUDESHORTS_HOST=127.0.0.1`) and prints both the local
  and LAN URLs (auto-detected IP). `cli serve` already took `--host`; the launcher
  now passes it. Verified: dashboard answers 200 on both 127.0.0.1 and the LAN IP
  (192.168.1.164); lan_ip detection works on macOS + Linux. So a phone/laptop on
  the network can open the desktop's dashboard.
- Auto-included ending slide: a pre-made outro image (auto-detected from
  `assets/`, e.g. `EndingSlide.png`; override via settings `video.endslide`) is
  normalized to 1080x1920 and appended both to the end of every video (held
  `video.endslide_seconds`, default 2.5s) and as the final carousel swipe. The
  timeline is extended so the audio track stays in sync. Verified on post 10:
  40.0s -> 42.5s video that ends on the outro frame; deck grew 5 -> 6 stills with
  the branded outro last. (`render/bridge.py::_endslide_path`, `renderer/render.mjs`.)
- Carousel deck preview in the dashboard: slide stills now show on the dashboard.
  `/media/{id}/slides/slide_NN.png` serves the stills (path-validated; traversal
  blocked), `review/queue.py::carousel_slides` lists a post's deck, the Review
  card shows a swipeable deck under the video, a new `/posts/{id}/carousel` page
  shows it full-size, and the Posts table links "Carousel (N)". New
  `templates/_carousel.html` + `carousel.html`, `static/carousel.js` (buttons +
  drag + arrow keys + live counter), CSS. Verified live (Playwright): inline +
  standalone render, next advances exactly one slide (0->428px, counter 1->2),
  real PNG bytes served, traversal/missing-slide -> 404.
- Batch generation (up to 20): `run_generate` clamps to 1-20, generates each
  post independently (one failure is logged + skipped, batch continues), and
  emits per-item progress. `cli generate` draws a live `rich` bar (spinner +
  current post + overall M/N + elapsed); per-post logging streams to the
  dashboard too. Verified: mock failure isolation (3 attempted, 2 created) +
  real --limit 2 run (both follow-ups, bar rendered).
- Wider topic range: expanded sources.yaml to 19 working feeds across general
  tech, AI/big-tech (incl. Nvidia/Google blogs), security (Krebs, Bleeping,
  TheHackerNews), hardware/chips (Tom's, IEEE, Register), and consumer/gaming
  (Engadget, Wired, Polygon); dropped dead AnandTech, disabled 403-ing Reddit.
  Added virality-aware "buzz" scoring (select.interest in settings) so high-
  interest stories win. Top-20 now spans 7 sources (was all Hacker News).
  Humanized the generation prompt (natural voice, no em dashes, no AI-slop) via
  the prompt, not a hard filter. Verified: post #5 has 0 em dashes, reads human.
- Swipeable slideshow / carousel export: renderer now writes one settled
  1080x1920 PNG per slide (slides/slide_NN.png); assemble_review + exporter
  carry the deck into the review bundle and every publish/<platform>/ folder.
  Verified on post #4 (6 stills, correct dims, exported to all 3 platforms).
- Verified full pipeline live (ingest -> generate -> render -> review); rendered
  post #4 to a valid 1080x1920 H.264 MP4 (45.9s, new pacing confirmed).
- Fixed RSS ingestion on macOS: feedparser's urllib fetch failed TLS; now fetch
  via httpx + parse bytes (claudeshorts/ingest/fetchers.py).
- Reading-time-aware slide pacing: slides now hold long enough to read their
  text (renderer/lib/timeline.mjs + render.mjs + config/settings.yaml) instead
  of a fixed 4s. Fixes "text scrolls too fast."
- Fixed macOS/Linux dashboard launcher Python/venv selection issue.
