# Build Progress

> Living project memory / **historical build log**, phase-by-phase and
> chunk-by-chunk. For the current-state architecture map (what exists today,
> how the pieces fit, what's deferred on purpose), read
> **`docs/ARCHITECTURE.md` first** — it supersedes the "Orientation for a
> fresh Claude session" section further down this file, which describes the
> pre-rebuild SQLite/Phase-0-6 world and is kept only for history.

## Status: MVP phases (0-6) COMPLETE, then superseded by the goal.md platform
## rebuild (14 chunks; 1-8 + chunk-1-Task-11 done, chunks 10-14 gated on
## human-provided credentials) — see `CHECKPOINT_LAST.md` for the latest
## session-by-session detail and `docs/ARCHITECTURE.md` for the current
## system shape.

The pipeline described in this file's phase log (SQLite, no job queue, no
REST API, no scheduler, no Telegram bot) was real and shipped, but has since
been substantially rebuilt: the store moved to Postgres/Supabase, a durable
job queue + self-contained scheduler replaced ad hoc threading, a `/api/v1`
REST API and a Telegram bot were added as new front ends onto a shared
`services/` layer, structured logging was unified, and the renderer gained
brand-color pinning + two new layout templates. **Read `docs/ARCHITECTURE.md`
for how the system actually works today** — everything below this point is
preserved as build history, not current-state documentation.

---

## ▶ Resume here (session handoff — 2026-06-01)

### Auto-included ending slide (2026-06-02)

Every render now ends on a pre-made outro image. `render/bridge.py::_endslide_path`
resolves it from settings `video.endslide` (repo-relative path; `""` disables) or
auto-detects an `assets/*.png` named like an outro (`EndingSlide.png`, `outro.png`,
…) and passes an absolute path in the spec. `renderer/render.mjs` normalizes it to
`width×height` (scale-to-cover + crop) once, appends it as a trailing timed
"slide" of `video.endslide_seconds` (default 2.5s) so the audio track and totals
stay in sync, fills those frames from the static image (no template render), and
copies it as the final `slides/slide_NN.png` so the swipe deck closes on the same
outro. Verified live (post 10, real Chromium+ffmpeg): 40.0s→42.5s, last video
frame is the outro, deck 5→6 stills.

### Carousel deck now visible in the dashboard (2026-06-02)

The carousel was *exported* (slide stills shipped to `publish/<platform>/`) but
never *shown* in the dashboard — the `/media` route refused anything but
`video.mp4`/`thumb.png` and no template rendered the deck. Now finished:

- `dashboard/app.py` — `/media/{id}/{name:path}` also serves
  `slides/slide_NN.png` (strict `_SLIDE_RE`, so the path-joined lookup can't be
  used for traversal); `_media_path` also falls back to the raw render dir. New
  `GET /posts/{id}/carousel` full-size deck page. Review + Posts routes now pass
  the per-post deck (filenames / count).
- `review/queue.py::carousel_slides(post_id)` — lists a post's deck stills
  (review bundle first, then render dir).
- UI: `templates/_carousel.html` (reusable swipeable deck), `carousel.html`
  (standalone page), deck embedded under the video in `review.html`, "Carousel
  (N)" link in `posts.html`, `base.html` gained a `scripts` block.
  `static/carousel.js` drives prev/next + click-drag + arrow keys + a live
  counter over a CSS scroll-snap track. CSS added to `static/app.css`.
- Verified live (Playwright + TestClient): inline deck on Review cards and the
  full-size `/posts/10/carousel` both render; next advances exactly one slide
  (scrollLeft 0->428, counter 1->2 of 5); slide PNGs serve real bytes; traversal
  and missing-slide both 404. Posts 4/5/10/11/12 have decks on disk.

### Batch generation up to 20 (2026-06-02)

`generate/runner.py::run_generate` now clamps to `MAX_BATCH=20` and generates
each post independently: a single bad item is logged and skipped instead of
aborting the whole batch. It takes an optional `on_progress` hook and logs per
post (so the dashboard SSE stream shows progress). `cli generate` draws a live
`rich` progress bar (spinner + current post + overall M/N + elapsed) and prints
`generated=X failed=Y`. Return type unchanged (successes list), so the cli /
orchestrate / dashboard callers needed no edits.

### Wider topics + humanization (2026-06-02)

`config/sources.yaml` now lists 19 live RSS feeds spanning general tech, AI /
big-tech (incl. Nvidia + Google first-party blogs), security, hardware/chips,
and consumer/gaming (each live-validated; dead AnandTech dropped; 403-ing Reddit
feeds disabled pending OAuth). Selection is virality-aware: `select.interest`
(settings) drives a `_buzz_score` in `generate/select.py` that boosts items
naming hot entities/actions, so the top picks span many sources instead of being
all Hacker News. The generation system prompt was broadened to the full tech
landscape and humanized (natural voice, no AI-slop, never em dashes) as a
writing instruction, not a hard filter. NEXT: batch generation (up to 20) with
per-post error isolation + a progress bar.

### Carousel / swipeable slideshow (2026-06-02)

The renderer now also emits one settled 1080x1920 PNG per slide
(`slides/slide_NN.png`), carried through `review/queue.py::assemble_review` and
`publish/exporter.py` into every `publish/<platform>/` folder, so a post can
ship as an Instagram/TikTok swipe deck as well as the auto-advancing video.

### Pacing fix (2026-06-02) — reading-time-aware slide holds

Slides used to hold for a fixed `video.seconds_per_slide` (4.0s) no matter how
much text they carried, so dense slides "scrolled too fast." Slide hold is now
reading-time aware: `clamp(read_lead_seconds + words/(reading_speed_wpm/60),
seconds_per_slide, max_seconds_per_slide)`, and TTS narration is never cut.
Changed `renderer/lib/timeline.mjs` (`perSlideDurations(slides, opts)` +
`readingHoldSeconds`), `renderer/render.mjs` (passes the new knobs from
`spec.video`), and `config/settings.yaml` (new `reading_speed_wpm`,
`read_lead_seconds`, `max_seconds_per_slide`; `seconds_per_slide` is now the
floor). Verified via a Node smoke test; a real Chromium+ffmpeg render still
needs eyeballing on the desktop. Generation was left unchanged.


**Latest commit on `main`: `37d7a84`** (the desktop fixes below; pushed).
(Note: `84dfa34`, `e10fc5d`, and `37d7a84` are **unsigned** — the managed
commit-signing service was returning `400 missing source`; earlier phases are
signed. Re-sign later if desired.)

### Desktop session (2026-06-02) - launcher repaired for moved checkout

The macOS launcher failed from `/Users/aryavora/Desktop/Business/claudeshorts`
with:

```text
ERROR: Package 'claudeshorts' requires a different Python: 3.9.6 not in '>=3.11'
```

Root cause: the checkout had been moved from `/Users/aryavora/Desktop/claudeshorts`;
the existing `.venv` still had generated scripts such as `.venv/bin/pip` and
`.venv/bin/claudeshorts` pointing at the old path. The launcher only checked
`.venv/bin/python`, so it treated the venv as valid and could still hit a stale
or wrong pip path during dependency installation.

Fixed `start-dashboard.sh` to validate the pip script too, recreate an old or
moved `.venv`, and run dependency install/init/serve through the selected venv
interpreter with `"$VENV_PYTHON" -m pip` and `"$VENV_PYTHON" -m claudeshorts...`.

Verified locally: `CLAUDESHORTS_PORT=8765 ./start-dashboard.sh` recreated the
venv with Python 3.13.13, installed dependencies, initialized the DB, started
Uvicorn, and served dashboard pages with 200 responses. `bash -n
start-dashboard.sh`, `.venv/bin/python -m claudeshorts.cli version`, and shebang
checks for `.venv/bin/pip` and `.venv/bin/claudeshorts` passed.

### ✅ Desktop session (2026-06-01) — full pipeline verified live + 2 real bugs fixed

Ran the whole pipeline on the actual macOS desktop for the first time. Env was
already provisioned (Python 3.13 venv + deps, Node 24, Playwright **Chromium**,
**ffmpeg 8.1**, `claude` CLI 2.1.159). Two real bugs surfaced and are fixed
(both **uncommitted** as of handoff — see "commit decision" below):

1. **Generation was fully broken.** `claude -p --output-format json` in CLI
   v2.1.159 now returns a **JSON array of stream events** (`[{type:system…},…,
   {type:result,result:"…"}]`), not the old `{"result":…}` envelope. Patched
   `generate/generator.py::_result_text` to find the terminal `type==result`
   event (and raise on `is_error`), with back-compat + assistant-text fallback.
2. **`review/` and `publish/` Python packages were missing from git.** Phase 4
   wrote that code into the **top-level `review/` and `publish/` dirs, which are
   gitignored** — so it was never committed; a fresh clone had only empty
   runtime dirs. `cli.py`, `dashboard/app.py`, and `orchestrate/runner.py` all
   imported the ghosts → `ModuleNotFoundError`. **Reconstructed both packages**
   (`claudeshorts/review/{__init__,queue,captions}.py`,
   `claudeshorts/publish/{__init__,exporter}.py`) to satisfy every call site.

**Verified live, end to end:** ingest (113 items) → select → generate (3 posts)
→ render (real Chromium+ffmpeg → valid **1080×1920 H.264** MP4s, 24–28s) →
`assemble_review` bundle → dashboard (all 8 pages 200 + media serving) →
approve → per-platform export to `publish/`. Post 1 export + post 2 CLI render
both confirmed; `compileall` + all import sites clean.

**Known issue (non-fatal):** the two **Reddit** sources now return `403 Blocked`
(unauthenticated `hot.json` is blocked). One bad source can't kill ingest. Fix
later via Reddit OAuth or drop them; other sources gave 113 items.

**Committed + pushed** to `main` as `37d7a84` (verified: the rebuilt packages
are in the pushed tree). Also **anchored the `.gitignore`** runtime-dir patterns
to repo root (`/review/`, `/publish/`, `/data/`, `/renders/`, `/output/`) — the
unanchored `review/`/`publish/` patterns were matching `claudeshorts/review|publish/`
and silently dropping the source, the exact mechanism that lost it originally.

### How to run it locally (desktop)
```bash
cd ~/Desktop/claudeshorts      # or wherever the clone lives
git pull origin main
rm -rf .venv                   # clear any stale venv
./start-dashboard.command      # macOS (double-click also works); .bat on Windows
```
The launcher finds a Python 3.11+ interpreter, builds `.venv`, installs deps,
inits the DB, and opens `http://127.0.0.1:8000`.

### Known local gotchas (last debugging session)
- **Python version**: macOS default `python3` is 3.9; the project needs 3.11+.
  User installed Python 3.13 — confirm it's on PATH (`which python3.13`). The
  launcher searches `python3.13/3.12/3.11` and recreates a too-old `.venv`.
- **Must `git pull` first**: an earlier failure was just running the *old*
  pre-fix launcher locally (it probed `import claudeshorts`, which succeeds from
  the repo dir even uninstalled, so it skipped `pip install` → `import typer`
  crash). Fixed in `e10fc5d` (now probes real deps: typer/fastapi/uvicorn/…).
- **Rendering needs Node + Chromium + ffmpeg**: `cd renderer && npm install &&
  npx playwright install chromium`, and install ffmpeg. Dashboard runs without
  them; only video render/export needs them. Default `audio.mode: silent`.
- **Generation auth**: default backend `claude_cli` (Claude Pro/Max via the
  `claude` CLI — run `claude login`). Or set an API key in the dashboard
  Settings page (saved to `.env`, switches backend to `api`).

### Good first things to do in the next session
1. Run the launcher on the desktop; fix whatever surfaces on first real run.
2. `claudeshorts run` (or the dashboard “Run daily pipeline”) end-to-end with
   live feeds + a real Chromium render; eyeball a produced MP4.
3. Tune the slideshow template (`renderer/templates/slideshow.html`) visually.
4. Wire humanlike TTS (`audio.tts.command`: Piper or edge-tts) + add music to
   `assets/music/`.
5. Later: real YouTube Data API uploader from the `publish/<platform>/` seam.

### Orientation for a fresh Claude session
- Read `CLAUDE.md` (conventions) then this file. Pipeline: `ingest → select →
  generate → render → review → publish`, orchestrated by
  `claudeshorts/orchestrate`, fronted by the `claudeshorts/dashboard` console.
- CLI entrypoint: `python -m claudeshorts.cli <cmd>` (`init-db`, `ingest`,
  `select`, `generate`, `render`, `serve`, `run`, `version`).
- State in SQLite `data/app.db` (gitignored): `items`, `posts`, `threads`,
  `post_threads`, `runs`, `pins`. Runtime dirs `data/ review/ publish/ renders/`
  are gitignored and regenerated.

---

### Done
- **Phase 6 — Operator dashboard** (`claudeshorts/dashboard/`)
  - Server-rendered FastAPI console (Jinja2 templates + `static/app.css`), now
    served by `cli serve`. Sections: Overview (counts + run/ingest/generate
    buttons), Review queue (moved from `review/app.py`), Articles (browse + add
    a manual article, *generate now* or *pin to future posts*), Posts (render /
    export / schedule), Schedule (future-posts queue), Threads (content memory),
    Runs history, Settings (connect Anthropic account + tune pipeline).
  - `dashboard/jobs.py` — in-process background-job runner; a logging handler on
    the `claudeshorts` logger fans records to the owning thread's job, streamed
    to the browser over **SSE** (`/jobs/{id}/stream`) for live logs.
  - `dashboard/auth.py` — Anthropic connection state: detect `claude` CLI +
    login, or paste an API key (persisted to gitignored `.env`, switches backend
    to `api`). `dashboard/settings_io.py` — read/write `settings.yaml` (drops
    comments on save; documented in the UI).
  - Store additions: `pins` table + `store/pins.py` (operator-flagged items;
    `select_topics` force-includes them, run_generate clears the pin);
    `posts.scheduled_for` column + `set_schedule`/`scheduled_posts`/`due_posts`;
    `insert_manual_item`, `get_item`, `latest_items`, `all_posts`,
    `status_counts`, `threads_with_posts`/`posts_for_thread`, `recent_runs`.
  - `generate_for_item()` — generate one post from a specific item (still detects
    follow-up threads). `publish_due_posts()` drains the schedule queue; the
    daily runner calls it at the tail.
  - Launchers: `start-dashboard.command` (macOS double-click), `start-dashboard.sh`
    (Linux), `start-dashboard.bat` (Windows) — venv + deps + renderer npm +
    init-db, then serve and open the browser.
  - **Verified** (TestClient + mocks): all GET pages 200; manual add→pin→select
    force-include; `generate_for_item` (mock) creates draft + clears pin;
    schedule/`due_posts`; settings round-trip; background job + SSE done event.
- **Phase 5 — Orchestration & daily scheduling**
  - `orchestrate/runner.py` — `run_pipeline()`: idempotent per-day (guarded by a
    new `runs` table), bounded retries on ingest/generate, structured logging,
    per-post render isolation. Flags: `limit`, `force`, `skip_render`.
  - `store/runs.py` + `runs` table — daily run log / guard.
  - Wired `cli run`. `deploy/` — systemd user `.service` + `.timer`, cron
    fallback, and full desktop setup README.
  - **Verified**: full run (2 posts, 1 follow-up, queued), idempotent skip,
    `--force`, `--skip-render`, run-log recording.

### Done (earlier) — Phase 4 — review queue + assisted publish

### Done
- **Phase 4 — Review queue + assisted publish**
  - `review/queue.py` — `assemble_review()`: on render, build
    `review/<date>/post_<id>/` (video.mp4, thumb.png, captions.md, manifest.json)
    and mark the post `rendered`. `pending_reviews()` lists rendered posts.
  - `review/captions.py` — per-platform caption/hashtag formatting (`captions.md`
    for review; `PLATFORM_CAPTION` reused by the exporter).
  - `review/app.py` — FastAPI dashboard (`cli serve`): lists pending posts with
    inline video preview + theme swatches + captions; Approve/Reject. Approve ->
    export; Reject -> status `rejected` (+note). Localhost only. Form body parsed
    directly (no python-multipart dep).
  - `publish/exporter.py` — `export_post()`: copy MP4 + per-platform caption.txt
    into `publish/<platform>/<date>/post_<id>/`; mark `exported` + stamp
    `published_at` (content memory).
  - `cli render` now also assembles the review folder; `cli serve` runs the app.
  - Store: `get_items`, `posts_by_status` helpers.
  - **Verified** via FastAPI TestClient: assemble, dashboard list, media serving,
    approve -> 3-platform export (+status/published_at), reject -> status+note.

## Status (history) — Phase 3 complete — Node renderer (HTML slideshow -> MP4)

### Done
- **Phase 3 — Node renderer**
  - `renderer/templates/slideshow.html` — punchy/animated vertical template
    (animated gradient blobs, kinetic headline + staggered bullets, channel
    watermark, logo outro). Themed per-post via injected CSS vars
    (`--primary/--secondary/--accent`, light/dark). Deterministic
    `window.__render(slide, localMs, globalMs)` so capture is reproducible.
  - `renderer/lib/timeline.mjs` — pure frame plan; TTS stretches a slide to fit
    its narration. `renderer/lib/ffmpeg.mjs` — pure ffmpeg/ffprobe arg builders
    (encode, thumbnail, music bed, narration timeline w/ ducked music, mux).
  - `renderer/render.mjs` — orchestrator: optional TTS synth -> Playwright frame
    capture -> ffmpeg encode -> audio (music/tts) -> mux. Audio modes:
    silent | music | tts (config-driven TTS command, e.g. Piper/edge-tts).
  - `claudeshorts/render/bridge.py` — builds the render spec (theme + slides +
    channel + logo data-URI + music pickup) and invokes the Node renderer.
  - Store: added `posts.theme_json` (+ additive migration); `insert_post`/
    `get_post`/runner now persist & return the per-post theme.
  - Wired `cli render <post-id>` with clean error handling.
  - **Verified**: timeline math + the full ffmpeg pipeline (encode/thumb/music/
    narration+ducked bed/mux) with REAL ffmpeg; theme migration + persistence +
    `build_spec`; bridge->Node wiring reaches Playwright. NOT verifiable in this
    container: actual Chromium capture (browser CDN blocked) — run
    `npx playwright install chromium` on the desktop.

## Status (history) — Phase 2 complete — Claude generation

### Done
- **Phase 2 — Claude generation**
  - `generate/select.py` — `select_topics()`: rank fresh items (source weight +
    recency), dedupe vs recently-used items, near-duplicate filter, and
    follow-up detection against open `threads` (topical token overlap).
  - `generate/schema.py` — `POST_TOOL` (Anthropic tool def) + `validate_post()`
    structural validator (3-7 slides, per-platform captions). Used by both
    backends so bad posts never persist.
  - `generate/generator.py` — `generate_post()` with two backends:
    - **`claude_cli` (default)**: shells out to the `claude` CLI under the user's
      **Claude Pro/Max subscription** (no API key). Tolerant JSON parsing of the
      `--output-format json` envelope (handles markdown fences/prose).
    - `api`: Anthropic SDK, forced tool use + prompt caching (needs key).
    Backend chosen via `model.backend` in settings.yaml.
  - `generate/runner.py` — `run_generate()`: select -> generate -> insert `posts`
    (status draft) -> upsert `threads` + `post_threads`. `generate_fn` injectable
    for tests.
  - `store/posts.py`, `store/threads.py` — content-memory data access.
  - Wired `cli select` and `cli generate`; CLI loads `.env` via python-dotenv.
  - **Verified**: selection/follow-up/schema/persist offline (mock generator);
    `claude_cli` parsing via mock envelope; **and a real end-to-end generation
    through the `claude` CLI subscription backend** produced a valid post.

### Done (earlier)
- **Phase 1 — News ingestion**
  - `claudeshorts/ingest/fetchers.py` — `fetch_source()` dispatch for source
    kinds `rss` (feedparser, UA-spoofed), `hackernews` (Algolia API), `reddit`
    (hot.json). Normalizes to the `items` shape, strips HTML, `content_hash()`
    dedupe key (normalized url+title).
  - `claudeshorts/ingest/runner.py` — `run_ingest()`: iterate sources, age-filter
    (`max_age_hours` / `--since`), dedupe via `INSERT OR IGNORE`, per-source stats;
    one bad source can't kill the run.
  - `claudeshorts/store/items.py` — `insert_item()` (returns False on dup) +
    `count_items()`.
  - Wired `cli ingest` (`--since`, `--limit`); `requirements.txt` added.
  - **Verified offline** (container network is allowlist-blocked): RSS parse +
    HTML strip, dedupe (2 stored then 0), age filter, unknown-kind error. Live
    fetch works on an open network (e.g. the desktop).

- **Phase 0 — Scaffold & config**
  - Python package `claudeshorts/` with subsystem stubs: `ingest`, `generate`,
    `render`, `publish`, `review`, `orchestrate`.
  - `pyproject.toml` (deps: anthropic, feedparser, httpx, typer, pyyaml, fastapi,
    uvicorn, jinja2, python-dotenv). Console script `claudeshorts`.
  - `claudeshorts/config.py` — repo paths + cached YAML loaders (`settings()`,
    `sources()`), `ensure_dirs()`.
  - `claudeshorts/store/` — SQLite schema + `init_db()` (idempotent). Tables:
    `items`, `posts`, `threads`, `post_threads`. Dedupe via unique
    `content_hash` index.
  - `config/settings.yaml`, `config/sources.yaml` (seed tech/AI feeds).
  - `claudeshorts/cli.py` — Typer CLI; `init-db` + `version` working, other
    commands are guarded stubs.
  - `renderer/` Node skeleton (`package.json`, `render.mjs` stub).
  - `.env.example`, `.gitignore` updated for `data/ review/ publish/`.
  - Project memory: this file + `CLAUDE.md`.

### Next / backlog (post-MVP)
- Run on the desktop end-to-end with live network + Chromium (the one path not
  testable in-container) and tune the slideshow template visually.
- Choose + wire the humanlike TTS engine (`audio.tts.command`: Piper or edge-tts)
  and add royalty-free music to `assets/music/`.
- Later: real publishing APIs (YouTube Data API first), starting from the
  `publish/<platform>/` export seam.

### Setup notes for the desktop
- Renderer needs a browser: `cd renderer && npm install && npx playwright install chromium`.
- For TTS audio: install a humanlike free engine and set `audio.tts.command`
  (Piper local, or `edge-tts`); drop music in `assets/music/`. Default audio is
  `silent` so renders work with no extra setup.

### Open decisions / notes
- **Generation backend = `claude_cli`** (Claude Pro/Max subscription via the
  `claude` CLI; no API key). `api` backend remains available. Set in
  `config/settings.yaml` -> `model.backend`.
- Publishing starts assisted/manual; API uploaders deferred.
- ffmpeg NOT installed in this container — needed for Phase 3 (present on desktop).
- **Container network is allowlist-blocked** (`Host not in allowlist`): live
  ingestion must be tested on the desktop. `api.anthropic.com` IS reachable; the
  `claude` CLI backend works here (verified with a real generation).
