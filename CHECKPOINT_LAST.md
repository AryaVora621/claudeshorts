# CHECKPOINT / RESUME REPORT - 2026-06-02

Agent: Claude (Opus 4.8). This is the authoritative "pick up here" doc. If
context was cleared, read this + `docs/PROGRESS.md` + `TASK_QUEUE.md` and you're
oriented.

## Where the work lives
- **Branch: `feature/carousel-wider-topics`** (pushed to `origin`).
- 4 commits ahead of `main`, all verified locally on the macOS desktop:
  ```
  f0ccbd0 Batch generation up to 20: resilient + live progress bar
  0898516 Wider tech topics + virality-aware selection + humanized voice
  063e396 Reading-time slide pacing + swipeable carousel export
  97d49ea Fix RSS ingestion: fetch feeds via httpx (macOS TLS)
  ```
- NOT touched (prior session, intentionally left): `start-dashboard.sh` (modified),
  `AGENTS.md` (untracked).
- `main` is unchanged. Nothing merged. No PR opened yet.

## What this branch adds (all DONE + verified)
1. **RSS ingestion fix** (`claudeshorts/ingest/fetchers.py`): `feedparser.parse(url)`
   fetched via urllib and failed TLS on macOS (CERTIFICATE_VERIFY_FAILED), so every
   HTTPS feed silently returned 0 items. Now fetch bytes with `httpx` (certifi) and
   parse those. All RSS feeds work.
2. **Reading-time slide pacing** (`renderer/lib/timeline.mjs`, `render.mjs`,
   `config/settings.yaml`): each slide is held long enough to read its text
   (clamp(lead + words/wpm, min, max)) instead of a fixed 4s. Knobs under `video:`:
   `seconds_per_slide` (floor), `reading_speed_wpm` (200), `read_lead_seconds`
   (0.8), `max_seconds_per_slide` (8). Verified: post #4 = 45.9s (was 24s).
3. **Swipeable carousel** (`renderer/render.mjs`, `review/queue.py`,
   `publish/exporter.py`): renderer also writes one settled 1080x1920 PNG per slide
   to `slides/slide_NN.png`; carried into the review bundle and every
   `publish/<platform>/<date>/post_<id>/slides/`. So a post ships as a TikTok/IG
   swipe deck AND the auto-advancing video. Verified on post #4 (6 cards, exported
   to all 3 platforms).
4. **Wider topics + virality scoring + humanized voice**
   (`config/sources.yaml`, `config/settings.yaml`, `generate/select.py`,
   `generate/generator.py`): 19 live RSS feeds across general tech, AI/big-tech
   (incl. Nvidia/Google blogs), security (Krebs, BleepingComputer, TheHackerNews),
   hardware/chips (Tom's, IEEE, The Register), consumer/gaming (Engadget, Wired,
   Polygon). Dead AnandTech dropped; 403-ing Reddit commented out (needs OAuth).
   `select.interest` buzz scoring boosts items naming hot entities/actions ->
   top-20 now spans 7 sources (was 100% Hacker News). Generation prompt broadened
   + humanized (natural voice, no AI-slop, NEVER em dashes) as a writing
   instruction, NOT a hard filter (no humanizer skill is installed). Verified:
   post #5 = 0 em dashes, reads human.
5. **Batch generation up to 20** (`generate/runner.py`, `cli.py`): `run_generate`
   clamps to MAX_BATCH=20, generates each post independently (one failure logged +
   skipped, batch continues), optional `on_progress` hook + per-post logging
   (streams to dashboard SSE). `cli generate` draws a live `rich` bar (spinner +
   current post + M/N + elapsed); prints `generated=X failed=Y`. Return type
   unchanged so cli/orchestrate/dashboard callers needed no edits. Verified: mock
   failure isolation (3 attempted -> 2 created) + real `--limit 2` run.

## Environment (this desktop, all present)
Python 3.13 venv (`.venv`), `claude` CLI 2.1.160 (logged in), node 24,
ffmpeg/ffprobe 8.1, Playwright Chromium. Backend = `claude_cli` (subscription).

## DB drafts available to eyeball/render (data/app.db, gitignored)
#3, #5, #8, #9 are `draft`. #4 already rendered (video + 6-slide carousel under
`renders/post_4/` and `review/2026-06-02/post_4/`). Render any: `... render <id>`.

## Duplicate-story dedup — DEPRIORITIZED (user: "some duplicates are fine")
Investigated but intentionally NOT changed. Findings preserved for later:
- Current dedup (`select.py`): skip a candidate if its TITLE tokens overlap an
  already-picked title by >= `_DUP_MIN_OVERLAP` (4). Too weak across outlets
  (same story, different phrasing shares few exact title tokens).
- Best approach found: IDF-weight shared title+summary tokens over the candidate
  pool (rare tokens like "spark"/"mythos" matter, common ones like "nvidia"/"ai"
  don't), dup if shared-rare mass / smaller-item mass is high. Caught Claude
  Mythos (0.50) and Instagram-hijack (0.38); RTX Spark needs care (false-merge
  risk: "Nvidia RTX Spark" HN title with no summary scored 1.0 vs unrelated Nvidia
  items). Needs a min-shared-token guard + summary presence. Not worth it now.

## To run on the HOME SERVER (next step, per user)
```bash
git fetch origin && git checkout feature/carousel-wider-topics && git pull
rm -rf .venv                     # if Python differs from this desktop
./start-dashboard.sh             # Linux; or start-dashboard.command on macOS
# then, end to end:
python -m claudeshorts.cli ingest          # live feeds
python -m claudeshorts.cli generate --limit 20   # batch w/ progress bar
python -m claudeshorts.cli render <post-id>      # video + slides/ carousel
python -m claudeshorts.cli serve                 # review dashboard :8000
```
Renderer needs `cd renderer && npm install && npx playwright install chromium`
plus ffmpeg. Outputs: `renders/post_<id>/` (video.mp4, thumb.png, slides/), the
review bundle, and `publish/<platform>/<date>/post_<id>/` (video + slides/ deck).

## Next / open (see TASK_QUEUE.md)
- Open a PR / merge to `main` once tested on the home server.
- Optional: dedup (above), dashboard carousel preview, parallel batch generation.

## Human decisions needed
- None blocking. User will test on the home server, then decide on merge.
