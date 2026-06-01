# Build Progress

> Living project memory. Update at the end of every phase so a fresh session
> resumes without re-deriving context. See the master plan for full detail.

## Status: ALL PHASES COMPLETE (0–5) — MVP pipeline end to end

The full pipeline is built and verified: `ingest -> select -> generate (Claude
subscription) -> render (themed animated MP4) -> review dashboard -> assisted
publish export`, with a once-daily idempotent runner + systemd/cron scheduling.
Content memory (threads) drives dedupe + follow-ups; per-post themes match the
news subject. Only Chromium frame-capture and live network steps are verified on
the desktop (blocked in this container); all logic is verified here.

### Done
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
