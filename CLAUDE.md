# CLAUDE.md — project conventions & memory

claudeshorts turns daily **tech/AI news** into short-form video/carousel posts
for YouTube, TikTok, and Instagram (brand: **fork.ai**). The social posts
*are* the newsletter.

**Before starting work, read `docs/ARCHITECTURE.md`** — it is the current-state
map of the whole system (pipeline, services/API/queue/scheduler/bot, data
model, config, what's built vs. explicitly deferred, and rules for proposing
changes). **Then read `docs/PROGRESS.md`** for the phase-by-phase build
history and the latest session handoff notes at its top.

## Architecture (see docs/ARCHITECTURE.md for full detail)
- **Python core** (`claudeshorts/`): `ingest → select → generate → render
  bridge → review queue → publish export`, all backed by a shared
  `services/` layer used by the CLI, the FastAPI dashboard, the `/api/v1`
  REST API, and a durable Postgres-backed job queue (`jobs/`) + a
  self-contained scheduler (`scheduling/`, no external cron needed).
- **Node renderer** (`renderer/`) turns a slides JSON spec into a 1080×1920
  MP4 via Playwright frame capture + ffmpeg, plus one PNG per slide for a
  swipeable carousel export. Three interchangeable layout templates
  (`slideshow`/`editorial`/`breaking`), chosen deterministically by keyword
  rules, not by the LLM.
- **Telegram bot** (`claudeshorts/telegram_bot/`) is a separate process — a
  thin HTTP client of the REST API, single-admin-chat gated.
- **State** lives in **Postgres (Supabase)**, not SQLite — see
  `claudeshorts/store/db.py` for the schema (`items`, `posts`, `threads` +
  `post_threads`, `runs`, `pins`, `jobs`, `schedules`).

## Conventions
- Config over code: tune behavior in `config/settings.yaml` and
  `config/sources.yaml`; access via `claudeshorts.config`.
- Runtime dirs `data/ review/ publish/ renders/` are gitignored; create them via
  `config.ensure_dirs()`.
- Business logic goes in `claudeshorts/services/` — the CLI, dashboard
  routes, REST API handlers, and job registry are all thin callers into it.
  Long-running work is queue-backed (`jobs/registry.py` maps a `job_type` to
  a `services/` function), not run inline in a request handler.
- Generation runs under the **Claude Pro/Max subscription** by default
  (`model.backend: claude_cli` shells out to the `claude` CLI — no API key).
  Host needs Claude Code installed + `claude login`. Three fallback backends
  exist (`api`, `local`, `openai_compat`) behind a shared `LLMProvider`
  Protocol — see `claudeshorts/generate/providers/`.
- Secrets only in `.env` (gitignored); see `.env.example`. Never paste a real
  secret value into a tracked file, even a credential-collection doc like
  `NEEDS_FROM_YOU.md` — reference `.env` by variable name instead.
- CLI is the entrypoint: `python -m claudeshorts.cli <command>` (or the
  `claudeshorts` console script).

## Operating principles
- **Review-gate first**: nothing publishes without human approval.
- **Assisted publishing**: export to `publish/<platform>/` for manual upload;
  real API/OAuth publishing and browser-automation publishing are both
  deferred on purpose (each needs a human-provided credential/login) — don't
  build around that gate without asking.
- **Content memory**: prefer follow-ups that build on prior posts over repeats;
  attribute sources; summarize only (no paywalled full-text scraping).
- **No auth on the dashboard/REST API** (LAN-only posture by design); the
  Telegram bot's admin-chat allowlist is the one auth check that's actually
  load-bearing, since it's the only internet-reachable surface.
