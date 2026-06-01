# Build Progress

> Living project memory. Update at the end of every phase so a fresh session
> resumes without re-deriving context. See the master plan for full detail.

## Status: Phase 2 complete — Claude generation

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

### Next: Phase 3 — Node renderer (HTML slideshow -> MP4)
- `renderer/templates/`: 9:16 (1080x1920) HTML/CSS slideshow driven by a post's
  slides JSON (title -> content -> outro, CSS animations).
- `renderer/render.mjs`: Playwright frame capture at config fps/slide -> ffmpeg
  H.264 MP4 + thumbnail. Audio optional/stubbed this phase.
- `claudeshorts/render/`: subprocess bridge Python -> Node (slides JSON -> MP4).
- Wire `cli render <post-id>`. Verify: render a Phase-2 post -> playable MP4.

### Open decisions / notes
- **Generation backend = `claude_cli`** (Claude Pro/Max subscription via the
  `claude` CLI; no API key). `api` backend remains available. Set in
  `config/settings.yaml` -> `model.backend`.
- Publishing starts assisted/manual; API uploaders deferred.
- ffmpeg NOT installed in this container — needed for Phase 3 (present on desktop).
- **Container network is allowlist-blocked** (`Host not in allowlist`): live
  ingestion must be tested on the desktop. `api.anthropic.com` IS reachable; the
  `claude` CLI backend works here (verified with a real generation).
