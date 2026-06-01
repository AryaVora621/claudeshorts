# Build Progress

> Living project memory. Update at the end of every phase so a fresh session
> resumes without re-deriving context. See the master plan for full detail.

## Status: ALL PHASES COMPLETE (0–5) + Phase 6 dashboard — MVP pipeline end to end

The full pipeline is built and verified: `ingest -> select -> generate (Claude
subscription) -> render (themed animated MP4) -> review dashboard -> assisted
publish export`, with a once-daily idempotent runner + systemd/cron scheduling.
Content memory (threads) drives dedupe + follow-ups; per-post themes match the
news subject. Only Chromium frame-capture and live network steps are verified on
the desktop (blocked in this container); all logic is verified here.

---

## ▶ Resume here (session handoff — 2026-06-01)

**Latest commit on `main`: `e10fc5d`.** Everything below is pushed to
`github.com/AryaVora621/claudeshorts`. (Note: `84dfa34` and `e10fc5d` are
**unsigned** — the managed commit-signing service was returning `400 missing
source` all session; earlier phases are signed. Re-sign later if desired.)

**Immediate goal: get the dashboard running on the macOS desktop** — the one
path never runnable in the cloud container (no live network allowlist, no
Chromium, no ffmpeg here). Everything else is built and unit-verified.

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
