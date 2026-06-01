# claudeshorts

Automated content pipeline that turns daily **tech/AI news** into short vertical
videos/slideshows for **YouTube Shorts, TikTok, and Instagram Reels** — the social
posts *are* the newsletter (channel: **Midnight Curiosity**, `@midnight.curiosity`).

Generation runs on a **Claude Pro/Max subscription** via the `claude` CLI (no API
key/metered cost). Everything is **review-gated**: the pipeline produces themed
videos into a local dashboard and you approve before anything is exported for
upload.

```
ingest ──▶ select ──▶ generate ──▶ render ──▶ review queue ──▶ publish export
(RSS/HN/   (rank +    (Claude:     (themed     (FastAPI         (per-platform
 Reddit)    follow-    slides +     animated    approve/         folders for
            ups)       captions +   MP4 via     reject)          manual upload)
                       theme)       Playwright
                                    + ffmpeg)
```

- **Content memory** (SQLite `threads`): dedupes covered stories and writes
  *follow-ups* that build on prior posts instead of repeating them.
- **Content-driven theming**: Claude picks a palette matching the news subject
  (Nvidia → green/black, Anthropic → clay/gray …), not the channel brand.
- **Audio**: silent, royalty-free music bed, or humanlike TTS (Piper/edge-tts) —
  config-driven.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -U pip setuptools wheel
.venv/bin/pip install -r requirements.txt
cd renderer && npm install && npx playwright install chromium && cd ..
claude login                                   # subscription auth (no API key)

.venv/bin/python -m claudeshorts.cli run       # ingest → generate → render → queue
.venv/bin/python -m claudeshorts.cli serve     # review dashboard @ 127.0.0.1:8000
```

Daily scheduling (systemd timer / cron) and full desktop setup: see
[`deploy/README.md`](deploy/README.md). Architecture and per-phase status live in
[`docs/PROGRESS.md`](docs/PROGRESS.md); conventions in [`CLAUDE.md`](CLAUDE.md).

## Subsystems (all built — phases 0–5)

1. **Ingestion** (`claudeshorts/ingest`) — RSS + Hacker News + Reddit, deduped.
2. **Generation** (`claudeshorts/generate`) — selection + follow-up detection +
   Claude structured slides/captions/theme.
3. **Renderer** (`renderer/`) — themed animated HTML slideshow → 1080×1920 MP4
   (Playwright frame capture + ffmpeg), optional music/TTS audio.
4. **Review + publish** (`claudeshorts/review`, `claudeshorts/publish`) — local
   approval dashboard → per-platform export folders.
5. **Orchestration** (`claudeshorts/orchestrate`) — idempotent daily runner +
   scheduling units.

## Config

- `config/settings.yaml` — posts/day, video geometry, model backend, audio mode,
  channel identity.
- `config/sources.yaml` — news feeds + per-source weights.
