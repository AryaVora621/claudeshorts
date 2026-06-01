# Build Progress

> Living project memory. Update at the end of every phase so a fresh session
> resumes without re-deriving context. See the master plan for full detail.

## Status: Phase 3 complete — Node renderer (HTML slideshow -> MP4)

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

### Next: Phase 4 — Review queue + assisted publish
- On render, assemble `review/<date>/<post-id>/` (video.mp4, thumb.png,
  captions.md per platform, manifest.json); set post status `rendered`.
- `claudeshorts/review/` FastAPI dashboard (`cli serve`): list pending posts,
  inline video preview, Approve/Reject.
- `claudeshorts/publish/`: on approve, export MP4 + per-platform captions to
  `publish/<platform>/<date>/`; mark `exported`; stamp `published_at`.
- Verify: serve -> approve -> files land in publish/<platform>/.

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
