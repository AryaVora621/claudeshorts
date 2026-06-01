# Build Progress

> Living project memory. Update at the end of every phase so a fresh session
> resumes without re-deriving context. See the master plan for full detail.

## Status: Phase 0 complete — scaffold & config

### Done
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

### Verified
- `python -m claudeshorts.cli --help` lists commands.
- `python -m claudeshorts.cli init-db` creates `data/app.db` with all tables.

### Next: Phase 1 — News ingestion
- Implement fetchers in `claudeshorts/ingest/` for rss / hackernews / reddit
  source kinds (see `config/sources.yaml`).
- Normalize to the `items` schema; dedupe on `content_hash`; honor
  `settings.ingest.max_age_hours` / `per_source_limit`.
- Wire `cli ingest` (with `--since`, `--limit`).
- Verify: run `ingest`, confirm fresh rows; rerun adds 0 dupes.

### Open decisions / notes
- Model defaults to `claude-sonnet-4-6` in `settings.yaml` (configurable).
- Publishing starts assisted/manual; API uploaders deferred.
- ffmpeg not yet installed in this environment — needed for Phase 3.
