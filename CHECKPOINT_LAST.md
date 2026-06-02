# CHECKPOINT - 2026-06-02

Agent: Claude (Opus 4.8). Mode: Debugger -> Builder.

## Completed this session
1. **Reading-time-aware slide pacing** (earlier today) — see TASK_QUEUE Done.
2. **Full pipeline verified live, end to end** on the desktop:
   - ingest -> select -> generate (claude_cli) -> render (Chromium+ffmpeg) -> review assembly.
   - Generated post #4, rendered a valid **1080x1920 H.264** MP4, 1377 frames,
     **45.9s** (6 slides at 6.5-8s each — confirms the new pacing is live; was
     24s under the old fixed 4s/slide). Review folder assembled (video, thumb,
     captions.md, manifest.json).
3. **Fixed a real ingestion bug**: every HTTPS RSS feed silently returned 0
   items. Root cause: `feedparser.parse(url)` fetches via Python's `urllib`,
   which fails TLS on macOS (`CERTIFICATE_VERIFY_FAILED`, no system CA bundle).
   Fix in `claudeshorts/ingest/fetchers.py::_fetch_rss`: fetch bytes with
   `httpx` (bundles certifi) then `feedparser.parse(bytes)`. Now techcrunch/
   theverge/arstechnica/arxiv all return items. (Reddit 403 is a separate,
   known issue — unauthenticated hot.json is blocked.)

## Completed (cont.)
4. **Swipeable slideshow / carousel export** (user's priority). The pipeline
   only made an auto-advancing MP4 before; now it also emits a swipe deck.
   - `renderer/render.mjs` — after video capture, render each slide at its
     settled state (all bullets in) and screenshot to `slides/slide_NN.png`;
     return `slides:[...]` in the result JSON.
   - `review/queue.py::assemble_review` — copy the deck into the review bundle
     (`slides/`) + list it in manifest.json.
   - `publish/exporter.py` — `_locate_slides()` + copy the deck into every
     `publish/<platform>/<date>/post_<id>/slides/` (TikTok/Instagram/YouTube).
   - Verified on post #4: 6 stills at 1080x1920, fully settled (eyeballed
     slide_01 + slide_05), exported to all 3 platform folders.

5. **Wider topics + humanization** (committed on branch).
   - `config/sources.yaml` — 19 working RSS feeds across general tech, AI/big-
     tech (+ Nvidia/Google first-party blogs), security (Krebs, BleepingComputer,
     TheHackerNews), hardware/chips (Tom's, IEEE Spectrum, The Register), and
     consumer/gaming (Engadget, Wired, Polygon). Live-validated each; dropped
     dead AnandTech; disabled the 403-ing Reddit feeds (commented, re-enable
     with OAuth).
   - `config/settings.yaml` `select.interest` + `select.py` `_buzz_score` —
     virality-aware ranking: score = source weight + recency + entity/action
     buzz. Top-20 now spans 7 sources (was 100% Hacker News).
   - `generate/generator.py` SYSTEM_PROMPT — broadened topic scope; humanized
     voice; NEVER em dashes + AI-slop ban, as a writing instruction (NOT a hard
     filter, per user). Verified: post #5 valid, 0 em dashes, reads human.

6. **Batch generation (up to 20)** (committed on branch).
   - `generate/runner.py::run_generate` — clamp to MAX_BATCH=20; each post
     generated independently inside the loop, wrapped in try/except so a bad
     item is logged + skipped (batch continues); optional `on_progress` hook +
     per-post logging (streams to dashboard SSE). Still returns the successes
     list, so cli/orchestrate/dashboard callers are unchanged.
   - `cli.py::generate` — live `rich` progress bar (spinner + current post +
     overall M/N + elapsed); prints `generated=X failed=Y` + the new post list.
   - Verified: mock failure isolation (3 attempted -> 2 created, no abort) and a
     real `--limit 2` run (posts #8, #9, both follow-ups, bar rendered).

## Next (per user / backlog)
- Tighter near-duplicate dedup across outlets (token overlap misses same story
  from different sites) — matters most for 20-post batches.
- Optional: dashboard carousel preview; parallelize batch generation.

## Verification commands
- `.venv/bin/python -m claudeshorts.cli ingest --limit 10`  (RSS now works)
- `.venv/bin/python -m claudeshorts.cli generate --limit 1` (post #4)
- `.venv/bin/python -m claudeshorts.cli render 4`           (valid MP4)
- `ffprobe ... renders/post_4/video.mp4`                    (h264 1080x1920 45.9s)

## Human decisions needed
- Approve the batch + wide-topics plan (see chat) before I implement.
