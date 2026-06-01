# Build Progress

> Living project memory. Update at the end of every phase so a fresh session
> resumes without re-deriving context. See the master plan for full detail.

## Status: Phase 1 complete — news ingestion

### Done
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

### Next: Phase 2 — Claude generation
- `claudeshorts/generate/`: Anthropic client (Sonnet 4.6, prompt caching on the
  static system prompt), `select` step (rank items, dedupe vs recent posts,
  detect follow-ups against `threads`), structured slides + per-platform captions
  via tool/JSON schema, upsert `threads` + `post_threads`.
- Wire `cli select` and `cli generate`; write rows to `posts` (status `draft`).
- Verify: generate on a stored item -> schema-valid `posts` row.

### Open decisions / notes
- Model defaults to `claude-sonnet-4-6` in `settings.yaml` (configurable).
- Publishing starts assisted/manual; API uploaders deferred.
- ffmpeg not yet installed in this environment — needed for Phase 3.
- **Container network is allowlist-blocked** (`Host not in allowlist`): live
  ingestion and any external API call must be tested on the desktop. Logic is
  verified offline here. Check whether `api.anthropic.com` is reachable before
  relying on live Phase 2 verification in-container.
