# Task Queue

## Open
- **USER-REQUIRED — chunk 1 Task 11**: run the real Supabase migration. Put the
  real Session Pooler URL (project `nddlutmilajkqtoygmfi`; DB password from the
  Supabase dashboard) into `.env` as `SUPABASE_DB_URL`, back up `data/app.db`,
  run `python -m scripts.migrate_sqlite_to_supabase data/app.db`, spot-check the
  dashboard. Until then the store runs against a local docker Postgres
  (`claudeshorts-test-pg`, port 54329, URL already in `.env`).
- **goal.md platform rebuild** (PLANNING COMPLETE, 14/14; implementation
  NOT started): all 14 chunks have committed specs under
  `docs/superpowers/specs/`, and all except 9/13 (research-only by
  design) have committed TDD plans under `docs/superpowers/plans/`. Next:
  user decides which chunk(s) to actually implement — chunks 1-9 have no
  human-required blockers and can start immediately; chunks 10-14 each
  have one explicitly-flagged human-required final step (real API
  keys/logins/tokens) within an otherwise-complete plan. Full detail in
  `CHECKPOINT_LAST.md`.
  New Supabase project `claudeshorts` (nddlutmilajkqtoygmfi) created for
  this; `adhdsat` project paused as part of the same decision.
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
- [IN_PROGRESS Claude/Fable5] goal.md rebuild implementation, chunks 1-8 via
  subagent-driven development on branch `feature/platform-rebuild`.
  **Chunks 1-4 code-complete** (chunk 1: store layer fully Postgres; chunk 2:
  durable job queue + worker; chunk 3: services/ layer, all frontends thin
  callers; chunk 4: REST API at /api/v1 — posts/articles/pipeline/jobs +
  health, 123/123 tests, live-smoke green incl. 404/409 error mapping).
  Only chunk 1's human-required Task 11 (real data migration) remains — see
  Open. Progress ledger: `.superpowers/sdd/progress.md`. Next: chunk 5
  (scheduling engine).
- [IN_PROGRESS Claude/Opus] Live jobs dashboard: percent bars (phase + per-item),
  clickable job history that survives restarts (new `jobs` SQLite table),
  embedded live terminal in the dashboard. Frontend + read-only progress
  instrumentation only (no stop/cancel, no change to what jobs do). See PLAN.md.

## Done
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
