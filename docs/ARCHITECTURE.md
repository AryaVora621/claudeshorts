# claudeshorts — Architecture

> **Audience**: any AI agent (or human) opening this repo cold. This is the
> "what is this and how does it actually work today" doc. `docs/PROGRESS.md`
> is the historical build log (phase-by-phase, chunk-by-chunk); this file is
> the current-state map. If the two ever disagree, trust the code, then this
> file, then PROGRESS.md.

## What this is

claudeshorts turns daily tech/AI news into short-form vertical video +
swipeable carousel posts (YouTube Shorts / TikTok / Instagram Reels format,
1080×1920) and pushes them through a human review gate before anything goes
out. It runs as a **daily automated pipeline** with a web dashboard, a REST
API, an optional Telegram bot, and a self-contained scheduler — no external
cron required. It is a solo-operator tool, not a multi-tenant SaaS: single
brand identity (`fork.ai`), single operator, LAN-only auth posture (no login
system — see "Security posture" below).

Brand: **fork.ai** — "AI & tech news, forked daily." Flat purple (`#A855F7`)
4-prong-fork mark on near-black (`#111111`), JetBrains Mono. Assets in
`Brandkit/fork/`.

## The pipeline (data flow, not code layout)

```
ingest → select → generate → render → review (human gate) → publish (export)
```

1. **Ingest** (`claudeshorts/ingest/`) — pulls RSS/HN/Reddit sources listed
   in `config/sources.yaml` (19 feeds: general tech, AI/big-tech, security,
   hardware, consumer/gaming), normalizes to a common `items` shape, dedupes
   by `content_hash` (normalized url+title). One bad source can't kill a run.
2. **Select** (`claudeshorts/generate/select.py`) — ranks fresh, unposted
   items (source weight + recency + a "buzz" virality score from keyword
   matching against `select.interest` in settings), dedupes near-duplicates,
   and detects follow-ups against open `threads` (topical token overlap) so
   a story can get a part-2 post instead of a flat repeat.
3. **Generate** (`claudeshorts/generate/`) — calls an LLM to turn a selected
   item into 3-7 slides + per-platform captions, validated against a
   structural schema (`generate/schema.py`) before it's ever persisted.
   Deterministic post-processing (no LLM) then pins a brand color by keyword
   match (`style_rules.py::pin_brand_colors`) and picks a layout template
   (`style_rules.py::select_layout`) — see "Providers" and "Styling" below.
4. **Render** (`claudeshorts/render/bridge.py` → `renderer/`) — builds a JSON
   spec from the post (theme, slides, layout, channel branding, audio) and
   hands it to a **Node.js/Playwright** renderer that captures each slide as
   a frame sequence in a real Chromium and muxes it to H.264 MP4 via ffmpeg.
   Also writes one settled PNG per slide (the swipeable carousel deck) and
   auto-appends a branded outro slide/frame.
5. **Review** (`claudeshorts/review/`) — assembles a review bundle
   (video, thumbnail, captions, slide stills, manifest) and surfaces it in
   the dashboard. **Nothing publishes without a human clicking Approve.**
6. **Publish** (`claudeshorts/publish/exporter.py`) — on approval, copies the
   video + per-platform caption into `publish/<platform>/<date>/post_<id>/`
   for manual upload. There is no direct API upload today (see "What's
   NOT built" below) — this is the "assisted publishing" seam a future
   YouTube/TikTok/Instagram API integration would plug into.

Everything above is also reachable as one idempotent daily run
(`services/pipeline_service.py::run_full_pipeline_service`, guarded by the
`runs` table so re-running the same day is a no-op unless `--force`).

## How the pieces talk to each other (system architecture)

There are three ways to drive the pipeline, all backed by the **same
service layer** — none of them contain business logic themselves:

```
CLI (claudeshorts/cli.py)  ─┐
Dashboard (FastAPI, HTML)  ─┼─→  claudeshorts/services/*  →  claudeshorts/store/* (Postgres)
REST API (/api/v1/*)       ─┘         ↑
Telegram bot (separate       claudeshorts/jobs/* (durable queue + worker)
  process, HTTP client   ─────────────┘
  of the REST API)
```

- **`claudeshorts/services/`** — the one place pipeline logic lives:
  `pipeline_service` (ingest/generate/render/full_run/generate_from_item),
  `posts_service` (approve/reject/schedule/export), `articles_service`
  (add/pin/unpin/generate-from-item), `reporting_service` (weekly report).
  CLI commands, dashboard routes, the REST API, and job handlers are all
  thin callers into these — if you're adding a new capability, it goes here
  first, then gets exposed through whichever surface needs it.
- **`claudeshorts/jobs/`** — a durable Postgres-backed job queue
  (`queue.py`: `enqueue`/`claim_next` via `FOR UPDATE SKIP LOCKED`/
  `complete`/`fail`+backoff/`cancel`/`pause`/`resume`), a polling `worker.py`
  daemon thread started at dashboard boot, and `registry.py` (a pure
  `job_type → service function` lookup table, no logic of its own). Long
  operations (ingest, generate, render, full runs) are queue-backed so the
  dashboard/API/bot never block on them — they enqueue and return a job id,
  the caller polls or streams progress.
- **`claudeshorts/scheduling/`** — a **self-contained** scheduler (no
  external cron/systemd needed, though `deploy/` has a systemd fallback for
  the old pre-queue design). A polling thread (`scheduler.py`) started
  alongside the worker checks `schedules` rows and enqueues jobs when due.
  Three defaults seeded on first boot from `config/settings.yaml`'s
  `schedule:` section: daily `full_run`, hourly `drain_scheduled_posts`
  (publishes anything the operator scheduled for later), weekly
  `weekly_report`.
- **`claudeshorts/api/`** — FastAPI router mounted at `/api/v1` inside the
  same app as the dashboard (`claudeshorts/dashboard/app.py`). No auth (LAN
  posture). Routers: `health`, `articles` (list/add/pin/unpin/generate),
  `posts` (list/get/approve/reject/schedule/export), `pipeline` (4
  queue-backed 202 endpoints: ingest/generate/render/run),
  `jobs` (list/get/cancel/pause/resume/**retry**), `profiles` (view-only,
  browser-automation profile metadata). Every handler is either a one-line
  `service_call` adapter (translates `ValueError`→404, `FileNotFoundError`
  →409) or a one-line queue call — if a handler ever grows real logic
  inline, that's a review-worthy smell, move it to `services/`.
- **`claudeshorts/dashboard/`** — server-rendered FastAPI + Jinja2 console
  (no frontend framework/build step). Pages: Overview, Review queue,
  Articles, Posts (+ carousel deck viewer), Schedule, Threads (content
  memory), Runs history, Jobs (live progress via SSE), Settings (connect
  Anthropic account, tune `settings.yaml`). `dashboard/jobs.py` streams job
  progress to the browser over Server-Sent Events by polling the `jobs`
  table.
- **`claudeshorts/telegram_bot/`** — a **separate process**
  (`python -m claudeshorts.telegram_bot`), not imported by the dashboard.
  It is a thin `ApiClient` (`client.py`) wrapping `/api/v1/*` over HTTP —
  it never touches `services/` or the DB directly, on purpose, so the REST
  API stays the one integration surface. Single-admin-chat authorization
  (`TELEGRAM_CHAT_ID` env var gates every command). Commands: `/queue`,
  `/generate`, `/approve`, `/reject`, `/retry`, `/profiles`, `/workers`,
  `/logs`. `notify.py` pushes proactive messages (job failure, weekly
  report ready) — wired into the job worker, not into the bot's own
  process.

## Data model (Postgres via Supabase)

`claudeshorts/store/db.py` owns the schema (additive `CREATE TABLE IF NOT
EXISTS` / `ADD COLUMN IF NOT EXISTS`, safe to run every boot). Access is
psycopg3 with `dict_row`, used as a context manager (commit on clean exit,
rollback on exception) — see any `claudeshorts/store/*.py` file for the
pattern.

| table | purpose |
|---|---|
| `items` | raw normalized news items from ingestion; `content_hash` unique index is the dedupe key |
| `posts` | generated content + lifecycle status (`draft → rendered → approved/rejected/scheduled → exported`); `slides_json`/`theme_json`/`captions_json` are native JSONB; `layout` picks the renderer template |
| `threads` / `post_threads` | content memory — an ongoing storyline (`threads`) that posts (`post_threads`, many-to-many) attach to, for dedupe and follow-up detection |
| `runs` | daily-run idempotency guard + log |
| `pins` | operator-flagged items that force-include into the next `select_topics` regardless of ranking |
| `jobs` | the durable queue — status vocabulary is **uppercase** (`PENDING/RUNNING/COMPLETED/FAILED/CANCELLED/PAUSED`); a handful of historical rows from before chunk 2 may still be lowercase, dashboard/API handle both |
| `schedules` | recurring job definitions (`daily_at` / `every_minutes` / `weekday` kinds); `next_run_at` and `enabled` are restart-safe (upsert never touches them) |

The store was originally SQLite (see PROGRESS.md phases 0-6); it was fully
migrated to Postgres/Supabase in the goal.md rebuild (chunk 1). The real
hosted project is `nddlutmilajkqtoygmfi`; `SUPABASE_DB_URL` in `.env` points
at it via the Session Pooler. There is no SQLite code path left — a local
docker Postgres (`claudeshorts-test-pg`) is used for the test suite instead.

## The renderer (`renderer/`, Node.js — separate runtime from the Python core)

Not a video-editing library — it's a **headless-browser frame-capture
pipeline**. `render.mjs` drives Playwright to load an HTML template with a
spec injected, calls a deterministic `window.__render(slideIndex, localMs,
globalMs)` contract once per frame at 30fps, screenshots each frame, and
pipes them through ffmpeg (`lib/ffmpeg.mjs`, pure arg-builder functions) to
H.264. `lib/timeline.mjs` computes reading-time-aware slide durations
(`clamp(read_lead + words/wpm, floor, cap)`, TTS narration never cut short).

Three interchangeable templates in `renderer/templates/`, all implementing
the same `window.__init(spec)` / `window.__render(...)` contract so
`render.mjs`'s capture loop needs zero changes to add a new one:
- `slideshow.html` — default, animated gradient blobs, kinetic headline
- `editorial.html` — calm, whitespace-heavy, serif, for deep-dive posts
- `breaking.html` — urgent, pulsing ticker banner, animated blob bg, fast
  bullet stagger

Layout choice is **config-driven, not LLM-driven**:
`config/settings.yaml`'s `styles.layout_rules` maps keyword lists (e.g.
"breaking"/"urgent" → `breaking`) to a layout name; `generate/style_rules.py
::select_layout` does first-match-wins over title+summary, default
`slideshow` if nothing matches. Same file's `styles.brand_colors` similarly
pins a known-entity's brand color (nvidia/anthropic/openai/google/meta/
microsoft) into the theme by longest-substring match against the subject —
also deterministic, no LLM involvement, applied post-generation in
`generate/runner.py`'s shared `_persist_post` path.

Audio is config-driven too (`audio.mode: silent | music | tts`); TTS uses an
external command template (Piper for local/free, or edge-tts) — no
audio-generation code lives in this repo, it shells out.

## LLM generation backends (`claudeshorts/generate/providers/`)

A `LLMProvider` Protocol with 4 interchangeable implementations, selected by
`model.backend` in `config/settings.yaml` via `providers/registry.py`:
- `claude_cli` (**default**) — shells out to the `claude` CLI, runs under
  the user's **Claude Pro/Max subscription**, no API key needed. Requires
  `claude login` on the host.
- `api` — Anthropic SDK directly, forced tool use + prompt caching, needs
  `ANTHROPIC_API_KEY`.
- `local` — generic OpenAI-compatible HTTP provider pointed at a local
  server (Ollama/llama.cpp/vLLM), for zero-cost self-hosted generation.
- `openai_compat` — the same generic provider pointed at a remote
  OpenAI-compatible vendor (OpenRouter/NVIDIA NIM/Gemini). Currently preset
  to OpenRouter's `openai/gpt-oss-120b:free` (chosen for native tool-calling
  support, required because generation forces a tool-call shape via
  `generate/schema.py::POST_TOOL`).

`local`/`openai_compat` both exist because a P40 GPU home server
(`aiserver@192.168.1.178`) is the eventual target for free local generation
— see `docs/PLAN_local_model.md` — not yet wired as the live default.

`generate/generator.py::generate_post` is a thin dispatcher: resolves a
provider from the registry, builds the right prompt shape for that backend,
calls `generate_structured`, validates the result against `POST_TOOL`'s
schema before returning. Adding a 5th backend means implementing the
`LLMProvider` Protocol and registering it in `registry.py` — nothing else
in the codebase needs to know it exists.

## Config system

Two YAML files, loaded via `claudeshorts/config.py` (cached, no restart
needed for most changes since services re-read `settings()` per call rather
than caching at import time):
- `config/settings.yaml` — everything behavioral: channel identity, posts/
  day, video geometry/pacing, audio mode, LLM backend + per-backend config,
  brand-color/layout style rules, job queue tuning, schedule defaults.
- `config/sources.yaml` — the RSS/HN/Reddit source list.

Secrets live only in `.env` (gitignored) — `SUPABASE_DB_URL`,
`ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`,
`OPENAI_COMPAT_API_KEY`. **Never duplicate a real secret value into a
tracked file** — `NEEDS_FROM_YOU.md` had an OpenRouter key accidentally
pasted into it once this session; GitHub's push protection caught it before
it reached origin. If you're filling in credential placeholders in a
tracked doc, reference `.env` by name, don't paste the value.

## Testing

`tests/` mirrors `claudeshorts/` (e.g. `tests/api/`, `tests/jobs/`,
`tests/generate/providers/`). Runs against a **real Postgres** — either the
hosted Supabase project or a local docker instance
(`claudeshorts-test-pg`, port 54329) depending on `.env`. A full run is
226 tests and takes 5-10+ minutes over a real remote connection — this is
normal, not a hang; don't kill it early without checking elapsed progress
first. `tests/jobs/conftest.py` has an **autouse fixture that unsets
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`** for every job test — this exists
because an early test of the failure-notification path fired a real
Telegram message to the operator's phone (the `.env` has live credentials
loaded process-wide). **Do not remove that fixture** without replacing it
with an equivalent guard.

## Security / operational posture

- **No auth on the dashboard or REST API** — designed for LAN-only access
  (`start-dashboard.sh` binds all interfaces by default for phone/laptop
  access on the same network, override with `CLAUDESHORTS_HOST=127.0.0.1`).
  Do not expose this to the public internet without adding auth first.
- **Telegram bot is single-admin-chat gated** (`TELEGRAM_CHAT_ID` allowlist)
  — the one surface in this stack that IS internet-reachable (Telegram's
  servers), so its auth check is load-bearing in a way the dashboard's
  isn't.
- **Human-in-the-loop by design** — nothing reaches `publish/` without an
  explicit Approve action. Don't add an auto-publish path without an
  explicit operator decision to do so.
- **Content policy**: summarize only, no full-text scraping of paywalled
  sources, attribute sources. This is a stated project value, not just a
  technical constraint — respect it even when a tool (e.g. a scraping MCP)
  makes bypassing it easy.

## What's built vs. what's explicitly deferred

Fully built and merged to `main`: ingest, select, generate (4 LLM backends),
render (3 layouts + brand-color pinning), review dashboard, assisted
publish export, durable job queue, self-contained scheduler, structured
logging (contextvar-based job_id/worker_id/platform on every log line),
REST API, Telegram bot (commands + proactive notifications).

**Explicitly NOT built** (each gated on a human decision/credential, tracked
in `NEEDS_FROM_YOU.md` and `TASK_QUEUE.md`, do not build without asking):
- Direct-API publishing to YouTube/TikTok/Instagram — currently
  folder-export only; a `PublishProvider` Protocol exists in the chunk-10
  design doc but was skipped in favor of folder export. Revisit only if the
  operator wants real API credentials + OAuth flows over the current manual
  upload.
- Browser-automation publish path (`browser_profile` provider) — YouTube
  Studio upload flow is fully implemented as the reference; TikTok/
  Instagram selectors are real-but-uncalibrated stubs. Needs a real logged-
  in session to calibrate.
- AI video clip generation (Veo/Higgsfield/Runway) — research-only so far
  (`docs/superpowers/specs/2026-07-10-chunk13-higgsfield-veo-research-note.md`).
  Real recurring cost (~$0.15-0.40/sec via Vertex AI Veo API), flagged as
  opt-in-only, never a default. A `flow_browser` UI-automation alternative
  was researched and found to have real ToS/detection risk — do not build
  it as a Playwright automation without re-reading that research note.
- Local LLM backend actually wired as default — `local`/`openai_compat`
  provider code exists and is tested, but generation still defaults to
  `claude_cli`. Plan in `docs/PLAN_local_model.md` targets a home P40 GPU
  server, currently unreachable/unconfigured.

## For an AI agent proposing changes here

1. **Business logic goes in `claudeshorts/services/`**, not in the CLI,
   dashboard routes, API handlers, or job registry — those are all thin
   callers by design (a review-loop finding in the goal.md rebuild
   explicitly flagged and reverted logic that leaked into route handlers).
2. **Long-running work is queue-backed.** If you're adding an operation that
   takes more than ~1s, add a `job_type` to `jobs/registry.py` pointing at a
   `services/` function, don't run it inline in a request handler.
3. **Styling/layout decisions are deterministic, not LLM-driven** — keyword
   rules in `config/settings.yaml` + pure functions in
   `generate/style_rules.py`. Keep it that way; don't ask the LLM to also
   pick colors/layouts, it already has one job (slides + captions).
4. **Every new LLM backend implements the `LLMProvider` Protocol** and
   registers in `providers/registry.py` — nothing else should need to
   change.
5. **Every new renderer layout implements `window.__init`/`window.__render`**
   and gets added to `render.mjs`'s explicit `LAYOUTS` allowlist (uses
   `Object.hasOwn`, not a truthy lookup — a truthy-lookup version was a real
   prototype-pollution bug caught in review, don't reintroduce it).
6. **Schema changes to Postgres are additive migrations** in `store/db.py`'s
   `SCHEMA` string (`ADD COLUMN IF NOT EXISTS`), run unconditionally on
   every `init_db()` call — there is no separate migration runner.
7. **Don't add auth, don't add auto-publish, don't add real API publishing
   credentials or OAuth flows** without the operator explicitly asking —
   these are standing deferred-on-purpose decisions, not oversights.
8. **Check `NEEDS_FROM_YOU.md` and `TASK_QUEUE.md`'s Open section** before
   assuming a "missing" feature is actually missing — several are
   intentionally gated on credentials/logins only the human operator can
   provide, and re-implementing around that gate (e.g. hardcoding a
   workaround) is almost always the wrong move.
