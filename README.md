# claudeshorts

Automated content pipeline that turns daily **tech/AI news** into short vertical
videos + swipeable carousels for **YouTube Shorts, TikTok, and Instagram Reels**
— the social posts *are* the newsletter (brand: **fork.ai**, "AI & tech news,
forked daily").

> **`config/settings.yaml`'s `channel.name`/`channel.handle` still say
> `"Midnight Curiosity"` / `@midnight.curiosity`** — a pre-rebrand value that
> was never updated when the brand moved to fork.ai (`Brandkit/fork/`). It
> feeds the on-screen watermark/outro on every rendered video. Update it in
> `config/settings.yaml` when ready to ship under the new brand.

Generation runs on a **Claude Pro/Max subscription** via the `claude` CLI by
default (no API key/metered cost); three other LLM backends are available
(API key, local, or a remote OpenAI-compatible vendor). Everything is
**review-gated**: nothing exports for upload without an explicit human
approval in the dashboard.

```
ingest ──▶ select ──▶ generate ──▶ render ──▶ review (human gate) ──▶ publish export
(RSS/HN/   (rank +    (LLM:        (themed     (dashboard/API/       (per-platform
 Reddit)    follow-    slides +     animated    Telegram bot:         folders for
            ups)       captions,    MP4 +       approve/reject)       manual upload)
                       then         carousel
                       deterministic via
                       brand color/  Playwright
                       layout)       + ffmpeg)
```

Everything above runs through a **durable Postgres-backed job queue** and a
**self-contained scheduler** (no external cron required), and is reachable
from three front ends over a shared `services/` layer: the CLI, the
dashboard, a `/api/v1` REST API, and a Telegram bot. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system map.

- **Content memory** (Postgres `threads`): dedupes covered stories and writes
  *follow-ups* that build on prior posts instead of repeating them.
- **Content-driven theming**: the LLM picks slide content; brand-color pinning
  and layout selection are then applied deterministically by keyword rules
  (not by the LLM) — e.g. a story naming Nvidia gets Nvidia's palette, a
  "breaking"-keyword story gets the urgent ticker-banner layout.
- **Audio**: silent, royalty-free music bed, or humanlike TTS (Piper/edge-tts) —
  config-driven.

## Quick start

**Easiest — the dashboard launcher** (sets up the venv + deps, then opens the
dashboard in your browser):

- **macOS**: double-click `start-dashboard.command`
- **Windows**: double-click `start-dashboard.bat`
- **Linux**: `./start-dashboard.sh`

From the dashboard you can connect your Anthropic account, run the pipeline,
review renders, manually add/generate articles, and schedule posts.

**Manual / CLI:**

```bash
python3 -m venv .venv && .venv/bin/pip install -U pip setuptools wheel
.venv/bin/pip install -r requirements.txt
cd renderer && npm install && npx playwright install chromium && cd ..
claude login                                   # subscription auth (no API key)

.venv/bin/python -m claudeshorts.cli run       # ingest → generate → render → queue
.venv/bin/python -m claudeshorts.cli serve     # dashboard @ 127.0.0.1:8000
```

The scheduler is self-contained (runs inside the app, no external cron/timer
needed for the current design); `deploy/README.md` documents a systemd
fallback from an earlier iteration. **Read
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) first** for the current-state
system map (pipeline, services/API/queue/scheduler/bot, data model, what's
built vs. deliberately deferred); [`docs/PROGRESS.md`](docs/PROGRESS.md) has
the phase-by-phase build history and session handoff notes; conventions live
in [`CLAUDE.md`](CLAUDE.md).

## Subsystems

1. **Ingestion** (`claudeshorts/ingest`) — RSS + Hacker News + Reddit, deduped.
2. **Generation** (`claudeshorts/generate`) — selection + follow-up detection +
   LLM-structured slides/captions (4 interchangeable backends), then
   deterministic brand-color/layout pinning.
3. **Renderer** (`renderer/`) — 3 interchangeable HTML/CSS layout templates →
   1080×1920 MP4 + swipeable carousel stills (Playwright frame capture +
   ffmpeg), optional music/TTS audio.
4. **Review + publish** (`claudeshorts/review`, `claudeshorts/publish`) — review
   folders + per-platform export; assisted (manual-upload) publishing. Real
   API/OAuth publishing is deliberately deferred pending platform credentials.
5. **Jobs + scheduling** (`claudeshorts/jobs`, `claudeshorts/scheduling`) — a
   durable Postgres-backed queue and a self-contained polling scheduler; long
   operations run as background jobs with live progress, not inline.
6. **Services** (`claudeshorts/services`) — the one place pipeline business
   logic lives; the CLI, dashboard, REST API, and job registry are all thin
   callers into it.
7. **REST API** (`claudeshorts/api`, mounted at `/api/v1`) — health, articles,
   posts, pipeline (queue-backed), jobs, profiles. No auth (LAN-only posture).
8. **Dashboard** (`claudeshorts/dashboard`) — server-rendered operator console
   (`cli serve`): overview + run controls, review queue, article browser /
   manual ingest, posts (+ carousel viewer), future-posts schedule,
   content-memory threads, run history, live job progress via SSE, and
   Settings to connect your Anthropic account. Double-click launchers for
   macOS/Windows/Linux.
9. **Telegram bot** (`claudeshorts/telegram_bot`, run separately via
   `python -m claudeshorts.telegram_bot`) — a thin REST API client with
   single-admin-chat authorization; commands to check the queue, trigger
   generation, approve/reject/retry, and check worker/profile status, plus
   proactive job-failure and weekly-report notifications.

## Config

- `config/settings.yaml` — posts/day, video geometry, model backend, audio mode,
  channel identity, brand-color/layout rules, job queue tuning, schedule
  defaults.
- `config/sources.yaml` — news feeds + per-source weights.
