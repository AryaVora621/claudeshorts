# CLAUDE.md — project conventions & memory

claudeshorts turns daily **tech/AI news** into short-form video/slideshow posts
for YouTube, TikTok, and Instagram. The social posts *are* the newsletter.

**Before starting work, read `docs/PROGRESS.md`** — it is the living build state
(current phase, what's done, what's next). Update it at the end of every phase.

## Architecture (build order 0 → 5)
- **Python core** (`claudeshorts/`) orchestrates: `ingest → select → generate →
  render bridge → review queue → publish export`.
- **Node renderer** (`renderer/`) turns slides JSON into a 1080×1920 MP4 via
  Playwright frame capture + ffmpeg.
- **State** lives in SQLite (`data/app.db`): `items` (raw news), `posts`
  (generated content + lifecycle), `threads` + `post_threads` (content memory
  for dedupe and follow-ups).

## Conventions
- Config over code: tune behavior in `config/settings.yaml` and
  `config/sources.yaml`; access via `claudeshorts.config`.
- Runtime dirs `data/ review/ publish/ renders/` are gitignored; create them via
  `config.ensure_dirs()`.
- Generation runs under the **Claude Pro/Max subscription** by default
  (`model.backend: claude_cli` shells out to the `claude` CLI — no API key).
  Host needs Claude Code installed + `claude login`. An `api` backend
  (`ANTHROPIC_API_KEY`) is available as a fallback.
- Secrets only in `.env` (gitignored); see `.env.example`.
- CLI is the entrypoint: `python -m claudeshorts.cli <command>` (or the
  `claudeshorts` console script).

## Operating principles
- **Review-gate first**: nothing publishes without human approval (Phase 4).
- **Assisted publishing**: export to `publish/<platform>/` for manual upload;
  API automation is deferred.
- **Content memory**: prefer follow-ups that build on prior posts over repeats;
  attribute sources; summarize only (no paywalled full-text scraping).
