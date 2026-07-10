# CHECKPOINT / RESUME REPORT - 2026-07-11 (implementation session — chunks 1-3 CODE-COMPLETE)

Agent: Claude (Fable 5), branch `feature/platform-rebuild`. SDD ledger:
`.superpowers/sdd/progress.md`.

## Chunk 3 (service layer extraction): DONE, reviewed, verified live
- New `claudeshorts/services/` package: posts_service (approve/reject/
  schedule/export_now — unified the export/publish-now duplicate),
  articles_service (add/pin/unpin/generate_from_item), pipeline_service
  (ingest/generate/render/full_run/generate_from_item).
- jobs/registry.py reduced to a pure lookup over pipeline_service. Trade-off
  (reviewer-verified, plan-mandated): importing the registry now eagerly
  loads the whole pipeline stack (no cycle, no playwright).
- Dashboard's 9 POST handlers and CLI's ingest/generate/render/run are thin
  service callers. render_post_service returns a dict (frames/duration_ms/
  audio_mode/review_dir); CLI keeps its rich output, job log keeps one-liner.
- Fix rounds during review: restored parity catches in approve/schedule
  (b584dc7); untracked accidental .opencode/.serena/goal.md artifacts +
  gitignored them (84e8259).
- Live-smoke caught a latent chunk-1 bug: templates string-sliced timestamp
  columns that psycopg returns as datetime → /posts 500. Fixed via
  tshort/tsfull/tsdate Jinja filters + full repo sweep (6 fixed, 12 safe)
  + page-rendering-with-rows regression tests (01cad0c).
- Verified: full suite 88/88; all 8 dashboard pages 200 with data present.
- Commits 32c626d..01cad0c.

## Next action
Chunk 4 (REST API over services) via the same SDD loop; then 5-8.
Human-required items unchanged (chunk 1 Task 11 real migration; chunks
10-14 blocked on user credentials — do not start).

---

## Chunk 2 (job queue + state machine): DONE, reviewed, verified live
- jobs table extended (queue columns via additive ALTERs; status vocab now
  uppercase state machine, historical lowercase rows still displayed).
- New `claudeshorts/jobs/` package: queue.py (enqueue/claim_next via FOR
  UPDATE SKIP LOCKED/complete/fail+backoff/cancel/pause/resume/cancel_claimed),
  registry.py (5 job types → pipeline calls, lazy imports), worker.py
  (polling daemon; started at dashboard startup).
- dashboard/jobs.py rewritten: enqueue + DB-polling SSE (same wire protocol);
  6 app.py call sites rewired; frontend status handling made
  vocabulary-aware (jobs.js/app.css/job.html).
- Review loop caught + fixed real bugs beyond the plan: stale locked_at,
  max_attempts=0 override, request_cancel clobbering terminal jobs, worker
  stranding cancel-flagged claimed jobs in RUNNING, stuck progress bars.
- Live e2e: real ingest job enqueued via HTTP → COMPLETED through the
  worker; SSE progress/done events observed. Full suite 55/55.
- Commits a73e3d6..1811369.

## Next action
Chunk 3 (service layer extraction) via the same SDD loop; then 4-8.
Human-required items unchanged (see chunk 1 entry below + TASK_QUEUE.md).

---

# CHECKPOINT / RESUME REPORT - 2026-07-10 (implementation session — chunk 1 CODE-COMPLETE)

Agent: Claude (Fable 5), branch `feature/platform-rebuild` (created off
`feature/carousel-wider-topics`). Executing chunks 1-8 via
superpowers:subagent-driven-development; ledger in `.superpowers/sdd/progress.md`.

## Chunk 1 (Supabase migration): tasks 1-10 of 11 DONE, reviewed, committed
- Store layer fully converted to Postgres/psycopg3 (db/items/posts/threads/
  pins/runs/jobs), public APIs unchanged, JSONB native, context-manager commits.
- New: tests/ (31 tests, all green), scripts/migrate_sqlite_to_supabase.py
  (dest-count verification, sequence reset, --force guard).
- Tests run against a LOCAL docker Postgres `claudeshorts-test-pg` (port 54329,
  password claudeshorts, URL in gitignored .env). Docker Desktop was started for
  this; container must be running for the suite to pass.
- Review findings fixed along the way: cli.py init-db no longer echoes None
  (227ef59); migration verify now checks destination counts + all-table test
  coverage (5e44281).
- Commits: ada2860..5e44281 (plan doc, task 1-10 feats/fixes).

## Task 11 = HUMAN-REQUIRED (do NOT automate): real migration to Supabase
project `nddlutmilajkqtoygmfi` needs the DB password → real Session Pooler URL
in .env, backup data/app.db, run the script, spot-check dashboard.

## Next action
Chunk 2 (job queue + state machine) via the same SDD loop; then chunks 3-8.
Chunks 10-14 remain blocked on user-supplied credentials — do not start them.

---

# CHECKPOINT / RESUME REPORT - 2026-07-10 (goal.md platform rebuild — PLANNING COMPLETE, 14/14, handoff to dynamic workflows)

Agent: Claude (Sonnet 5), branch `feature/carousel-wider-topics`.

## Status: ALL 14 chunks speced + planned. Zero code implemented yet.
## The 10m `/loop` cron has been CANCELLED (confirmed via CronList: no
## scheduled jobs remain). The user is clearing context and setting up
## dynamic workflows to begin implementing the humanless parts (chunks 1-9,
## which have no human-required blockers) — this checkpoint is the handoff
## document for that fresh session.

### Chunk 13 addendum (2026-07-10, same day): Google AI Pro / Veo
The user has a **Google AI Pro** subscription ($20/mo) and asked if it
already covers Veo access. Researched and updated
`docs/superpowers/specs/2026-07-10-chunk13-higgsfield-veo-research-note.md`
with the finding: **Pro's Veo access is an app/UI quota (Gemini app: ~3
Veo 3 Fast gens/day; Google Flow web app: ~1,000 monthly AI credits),
NOT free Vertex AI API credit** — the pay-per-second API pricing
($0.15-0.40/sec) still applies regardless of the subscription; the
subscription's quota only works through Google's own Flow/Gemini web UIs.
**The actionable insight:** chunk 11's browser-profile automation pattern
(Playwright + a logged-in session, already designed to drive YouTube
Studio's upload flow) could equally drive `labs.google/fx/tools/flow`
to generate clips using the subscription's included quota at zero
marginal cost — third-party precedent for batch-automating Flow via
browser extensions was found during this research, confirming viability.
This doesn't solve full-volume generation (quota caps around 3-5
clips/day on Pro, ~100/month via Flow credits on Ultra, versus
`posts_per_day: 3` x ~5 slides needing ~450/month) but comfortably covers
an opt-in "one hero clip per top post" usage pattern. **Not built yet** —
still a "when you're ready to proceed" item, now with a cheaper first
option identified (`flow_browser` provider before `veo_api`/Vertex AI).

Chunks 11-14 landed since the "update 2" entry below:
11. Browser-automation profile system — `docs/superpowers/specs/2026-07-10-chunk11-browser-profiles-design.md` + plan (profile metadata in `config/profiles/*.yaml`, session state gitignored under `/profiles/`; goal.md's no-sleep/resilient-selector/mandatory-failure-capture rules built into `browser/wait.py`/`errors.py`; Playwright analytics scraper fills chunk 5's "pending" placeholder; a 4th `PublishProvider`, `browser_profile`, added to chunk 10's registry — YouTube Studio's upload flow fully implemented as the reference, TikTok/Instagram left as real-but-calibration-pending stubs)
12. Telegram bot interface — `docs/superpowers/specs/2026-07-10-chunk12-telegram-bot-design.md` + plan (bot is a pure HTTP client of chunk 4's REST API, never duplicates service logic; single admin chat only; profiles view-only; two small REST additions — `GET /profiles`, `POST /jobs/{id}/retry` — fill real gaps chunk 4 didn't cover)
13. Higgsfield + Veo research note — `docs/superpowers/specs/2026-07-10-chunk13-higgsfield-veo-research-note.md` (research only, no plan; **key finding: AI video clips are a real recurring cost, ~$340/month at current posts_per_day, not a marginal add-on** — recommend implementing only as an opt-in per-channel/per-post upgrade, never a default, whenever the user decides the cost is worth it)
14. Additional LLM provider API keys — `docs/superpowers/specs/2026-07-10-chunk14-llm-provider-keys-design.md` + plan (chunk 7's abstraction was already sufficient; this chunk adds copy-paste vendor config presets, a setup doc, and a `test-model-backend` CLI command so wiring a real key later is friction-free)

**The 14-chunk goal.md platform rebuild planning effort is now complete.**
Every chunk has a committed spec (`docs/superpowers/specs/2026-07-10-chunk*`)
and, except chunks 9/13 (explicitly research-only by design), a committed
TDD implementation plan (`docs/superpowers/plans/2026-07-10-chunk*`).
**No code has been implemented for any chunk yet** — this was a planning-
only phase per the standing `/goal` directive. **The `/loop 10m continue
working` cron has been cancelled** (user is moving to dynamic
workflow-based implementation instead — see the top of this file for the
handoff note). Chunks 1-9 have no human-required blockers and are ready
to implement immediately; chunks 10-14 each have one explicit
human-required final step (see below) but are otherwise fully planned.

### What's still genuinely human-required across the whole rebuild
- Chunk 1: run the real Supabase migration (schema + data) end to end.
- Chunk 10: obtain YouTube Data API / TikTok Content Posting API /
  Instagram Graph API credentials.
- Chunk 11: run `interactive_login.py` for real channel logins; calibrate
  TikTok/Instagram upload selectors against a real session.
- Chunk 12: create a real Telegram bot via BotFather, set
  `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`.
- Chunk 13: decide whether the ~$340/month AI-video-clip cost is worth
  paying for any subset of content, then implement if so.
- Chunk 14: obtain and paste in a real OpenRouter/NVIDIA/Gemini API key
  (or run a local Ollama/LM Studio/vLLM server).
None of these block implementing chunks 1-9's plans right now.

---

# CHECKPOINT / RESUME REPORT - 2026-07-10 (goal.md platform rebuild — planning phase, update 2)

Agent: Claude (Sonnet 5), branch `feature/carousel-wider-topics`.

## Status (superseded — see 14/14 entry above): 10 of 14 chunks fully speced + planned (docs only, no implementation yet)

Chunks 7-10 landed since the last checkpoint entry below:
7. LLM provider abstraction — `docs/superpowers/specs/2026-07-10-chunk7-llm-provider-design.md` + plan (`LLMProvider` Protocol; `claude_cli`/`api` moved verbatim; one `OpenAICompatibleProvider` class registered twice as `local`/`openai_compat`, covering Ollama/LM Studio/vLLM and OpenRouter/NVIDIA/Gemini/OpenAI without per-vendor code)
8. More video/renderer styles — `docs/superpowers/specs/2026-07-10-chunk8-video-styles-design.md` + plan (deterministic brand-color pinning by topic keyword — e.g. green for Nvidia, orange for Anthropic — plus 2 new layout templates, `editorial` and `breaking`, alongside today's `slideshow`; layout choice is config-driven keyword rules, not a new LLM field)
9. Remotion research note (chunk originally called "Contexto" — a mishearing the user corrected to Remotion) — `docs/superpowers/specs/2026-07-10-chunk9-remotion-research-note.md`; recommendation: do not migrate the current Playwright+FFmpeg renderer to Remotion now, no clear win and real migration cost; revisit only if a concrete pain point shows up
10. Publishing plugins + multi-channel posting — `docs/superpowers/specs/2026-07-10-chunk10-publishing-plugins-design.md` + plan (`PublishProvider` Protocol; `FolderExportProvider` = today's assisted export, channel-scoped; 3 credential-gated API stub providers for YouTube/TikTok/Instagram, real network calls deferred to a final human-required task; full multi-channel data model built now — `channels` table, `posts.channel_id`, deterministic `select_channel` routing — even though only 1 channel exists today)

**Real gap found while planning chunk 10:** this repo has **no `tests/`
directory at all** yet — every prior chunk's plan (1-9) that said "extend
existing test file X" was actually describing a file that doesn't exist.
Not a blocker (TDD steps create new files regardless), but whoever
executes chunk 1's plan first will need to also create `tests/conftest.py`
with a DB fixture — chunk 10's plan does this defensively (checks for it,
creates if absent) and future chunk plans should do the same rather than
assuming it exists.

## Status (original entry): 6 of 14 chunks fully speced + planned (docs only, no implementation yet)

User's goal.md describes a full platform rebuild (plugin providers, job
queue, service layer, REST API, Telegram bot, scheduling, multi-channel
publishing, Raspberry Pi deployment). Decomposed into 14 chunks (see
`TASK_QUEUE.md` and this session's task list), human-required chunks
(logins/API keys) pushed to the end per user instruction. Current /goal:
"continue working and chunking out plans for this large project, pause
only when needed to ask user or planning is done" — confirmed scope is
**planning** (spec + plan docs), not implementation, until told otherwise.

A cron job (`continue working` every 10 min) is active in this session to
keep this loop going; each firing should pick up the next pending chunk.

### Real infra changes made (not just docs)
- Paused Supabase project `adhdsat` (rhhpshsyrvckouqtyeov) — unrelated to
  this project, paused per user request.
- Created new Supabase project **`claudeshorts`** (id `nddlutmilajkqtoygmfi`,
  region `us-east-1`, free tier, $0/month) — this is the target datastore
  for chunk 1's migration once implemented.

### Chunks done (spec + plan committed, no code written yet)
1. Supabase schema + migrate off SQLite — `docs/superpowers/specs/2026-07-10-chunk1-supabase-migration-design.md` + plan
2. Job queue + state machine — `docs/superpowers/specs/2026-07-10-chunk2-job-queue-design.md` + plan
3. Service layer extraction — `docs/superpowers/specs/2026-07-10-chunk3-service-layer-design.md` + plan
4. REST API over services — `docs/superpowers/specs/2026-07-10-chunk4-rest-api-design.md` + plan
5. Scheduling engine — `docs/superpowers/specs/2026-07-10-chunk5-scheduling-engine-design.md` + plan (self-contained recurring scheduler; weekly report has an honest "pending Playwright analytics" placeholder, real cross-platform engagement deferred to chunk 11 per user's choice of Playwright scraping over platform APIs)
6. Structured logging overhaul — `docs/superpowers/specs/2026-07-10-chunk6-structured-logging-design.md` + plan

### Next action (superseded — see chunks 7-10 note above)
Chunk 11: browser-automation profile system + Playwright-based analytics
scraper (feeds chunk 5's weekly report). Then chunks 12-14 (Telegram bot,
Higgsfield/Veo, additional LLM keys) — these need API keys/logins from the
user, per their explicit "leave human-required tasks for last" instruction.

### Human decisions needed
None blocking right now — next chunks proceed with reasonable defaults,
flagging real decisions via AskUserQuestion as they come up (this has been
the working pattern: DB access approach, data migration scope, cancel/pause
depth, API auth, etc., each confirmed before writing the spec).

---

# CHECKPOINT / RESUME REPORT - 2026-06-10 (launcher PATH fix)

Agent: Codex.

## Status: fixed locally, ready for user test
The macOS/kitty launcher failure was reproduced with a minimal Finder-like PATH:

```text
PATH=/usr/bin:/bin:/usr/sbin:/sbin ./start-dashboard.sh
```

Root cause: Python 3.13 was installed in normal macOS locations
(`/opt/homebrew/bin`, `/usr/local/bin`, and the python.org framework path), but
the launcher only checked command names visible through the inherited PATH. Some
double-click or kitty launches do not load the user's shell profile, so the
launcher reported that Python 3.11+ was missing even though it was installed.

## What changed
- `start-dashboard.sh` now prepends standard macOS local install paths to PATH
  before probing tools.
- `find_python()` now also checks `.venv/bin/python`, Homebrew Python paths,
  `/usr/local/bin` Python paths, and python.org framework paths by absolute path.

## Verified
- `bash -n start-dashboard.command start-dashboard.sh`
- Minimal-PATH `./start-dashboard.sh` on port 8765: found
  `/opt/homebrew/bin/python3.13`, started the dashboard, and served `/` with
  HTTP 200. The test server was stopped cleanly.
- Minimal-PATH `./start-dashboard.command` on port 8766: found
  `/opt/homebrew/bin/python3.13`, started the dashboard, and served `/` with
  HTTP 200. The test server was stopped cleanly.

## Next action
User can run `./start-dashboard.command` or double-click it and test the
dashboard normally.

## Human decisions needed
None for this launcher fix.

---

# CHECKPOINT / RESUME REPORT - 2026-06-02 (carousel deck in dashboard)

Agent: Claude (Opus 4.8), branch `feature/carousel-wider-topics`.

## Status: DONE + verified live (UNCOMMITTED working-tree changes)
The carousel deck now appears in the dashboard. It was already exported to
`publish/<platform>/` but was never displayed: the `/media` route only served
`video.mp4`/`thumb.png` and no template rendered the slides. Finished end to end
and verified live with Playwright. Nothing committed yet.

## What was built this session
- `claudeshorts/dashboard/app.py`
  - `/media/{post_id}/{name:path}` now also serves `slides/slide_NN.png`, gated
    by `_SLIDE_RE = ^slides/slide_\d{2,}\.png$` (blocks path traversal); the
    earlier exact-name allowlist stays for video/thumb. `_media_path` also falls
    back to `renders/post_<id>/` after the review bundle.
  - New `GET /posts/{id}/carousel` -> full-size deck page.
  - Review + Posts routes pass per-post deck info (`decks`).
- `claudeshorts/review/queue.py` — new `carousel_slides(post_id)` -> sorted slide
  filenames (review bundle first, then render dir; [] for pre-carousel posts).
- Templates: new `_carousel.html` (reusable swipeable deck; `pid`, `slides`,
  optional `variant="inline"`) and `carousel.html` (standalone page). `review.html`
  embeds the deck under the video; `posts.html` adds a "Carousel (N)" link;
  `base.html` gained a `{% block scripts %}`.
- `static/carousel.js` — prev/next, click-drag, arrow keys, live `n/total`
  counter over a native CSS scroll-snap track (progressive enhancement).
- `static/app.css` — `.carousel*` component + `.deck-label`/`.deck-stage`.

## Verified (this session)
- TestClient: `/review` (markup present), `/posts`, `/posts/10/carousel` all 200;
  `/media/10/slides/slide_01.png` -> 200 image/png (647 KB); `/media/10/video.mp4`
  -> 200; traversal `slides/../../../etc/passwd` -> 404; `slide_99.png` -> 404;
  Posts page contains the carousel link. Decks exist for posts 4/5/10/11/12.
- Playwright (live server on :8791): Review cards show video + inline deck;
  `/posts/10/carousel` renders full size; clicking next scrolled exactly one
  slide (scrollLeft 0->428 == clientWidth) and the counter went 1->2 of 5.
- `node --check carousel.js` passed. Test artifacts (screenshots, .playwright-mcp)
  cleaned; test server stopped.

## Also this session: auto-included ending slide
The carousel + jobs dashboard work was committed as `ecdc095`. Then added an
auto-included outro slide (committed separately — see git log):
- `assets/EndingSlide.png` (941x1672 source) is normalized to 1080x1920 and
  appended to every video (held `video.endslide_seconds`, default 2.5s) AND as
  the final carousel still.
- `render/bridge.py::_endslide_path` auto-detects an outro image in `assets/`
  (or honors settings `video.endslide`; `""` disables) and passes an absolute
  path in the render spec. `renderer/render.mjs` normalizes it, extends the
  timeline by one trailing "slide" (keeps audio in sync), fills those frames
  from the image, and copies it as the last `slides/slide_NN.png`.
- Verified live (post 10, real Chromium+ffmpeg): 40.0s->42.5s, +75 frames, last
  video frame = the outro, deck 5->6 stills (slide_06 = branded outro).

## Re-rendered the review queue with the new outro (2026-06-02)
Posts 12, 11, 10, 5 (status `rendered`) re-rendered + re-assembled so the
dashboard decks and videos carry the outro. Verified: review bundles now hold
7/6/6/6 stills, each deck's last still is byte-identical (the same normalized
outro, md5 56e1883c07), videos are 49.9/42.5/42.5/42.2s. Left exported posts
(1, 4) and rejected post 2 untouched so shipped content isn't altered; drafts
(3, 8, 9) were never rendered. (These live in gitignored review/ + renders/, so
nothing to commit.)

## Pushed + LAN dashboard + local-model plan (2026-06-02)
- Pushed `feature/carousel-wider-topics` to origin (commits up to the LAN work).
- LAN-accessible dashboard: `start-dashboard.sh` now binds `${CLAUDESHORTS_HOST:-0.0.0.0}`
  (all interfaces) so other LAN devices can reach the desktop's dashboard; passes
  `--host` to `cli serve` and prints local + auto-detected LAN URLs. Override with
  `CLAUDESHORTS_HOST=127.0.0.1`. Verified: 200 on 127.0.0.1 AND 192.168.1.164.
- Local-model backend: PLAN ONLY, written to `docs/PLAN_local_model.md` (Qwen3-30B-A3B
  GGUF on the P40; fp8 impossible on Pascal -> use Q4/Q5 GGUF via Ollama/llama.cpp;
  new `local` backend reusing JSON-in-prompt + validate_post). Not implemented.

## BLOCKED
- Home server `aiserver@192.168.1.178` unreachable (incomplete ARP from a same-
  subnet machine, 192.168.1.164). User is fixing the Linux box; deferred. The
  server end-to-end test + the local-model build wait on this.

## NEXT (resume here)
1. When the server is back: pull the branch, run the launcher (now LAN-bound),
   do the end-to-end test, then open a PR / merge to main.
2. Local model: get user's calls on the open decisions in `docs/PLAN_local_model.md`
   (Ollama vs llama.cpp, quality bar, quant target), then implement the `local`
   backend.

## Human decisions needed
- The 3 open decisions in `docs/PLAN_local_model.md` (inference server, quality
  trade-off, quant target).
