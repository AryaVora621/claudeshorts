# Task Queue

## Open
- Better near-duplicate dedup for big batches: token-overlap dedup misses the
  same story across outlets (e.g. 3 "Anthropic IPO" items ranked top). Matters
  once batches are 20. Consider tighter/semantic dedup.
- Optional: surface the carousel deck in the dashboard review page (preview).
- Optional: parallelize batch generation (run a few claude CLI calls at once).

## In-Progress
- None.

## Done
- Batch generation (up to 20): `run_generate` clamps to 1-20, generates each
  post independently (one failure is logged + skipped, batch continues), and
  emits per-item progress. `cli generate` draws a live `rich` bar (spinner +
  current post + overall M/N + elapsed); per-post logging streams to the
  dashboard too. Verified: mock failure isolation (3 attempted, 2 created) +
  real --limit 2 run (both follow-ups, bar rendered).
- Wider topic range: expanded sources.yaml to 19 working feeds across general
  tech, AI/big-tech (incl. Nvidia/Google blogs), security (Krebs, Bleeping,
  TheHackerNews), hardware/chips (Tom's, IEEE, Register), and consumer/gaming
  (Engadget, Wired, Polygon); dropped dead AnandTech, disabled 403-ing Reddit.
  Added virality-aware "buzz" scoring (select.interest in settings) so high-
  interest stories win. Top-20 now spans 7 sources (was all Hacker News).
  Humanized the generation prompt (natural voice, no em dashes, no AI-slop) via
  the prompt, not a hard filter. Verified: post #5 has 0 em dashes, reads human.
- Swipeable slideshow / carousel export: renderer now writes one settled
  1080x1920 PNG per slide (slides/slide_NN.png); assemble_review + exporter
  carry the deck into the review bundle and every publish/<platform>/ folder.
  Verified on post #4 (6 stills, correct dims, exported to all 3 platforms).
- Verified full pipeline live (ingest -> generate -> render -> review); rendered
  post #4 to a valid 1080x1920 H.264 MP4 (45.9s, new pacing confirmed).
- Fixed RSS ingestion on macOS: feedparser's urllib fetch failed TLS; now fetch
  via httpx + parse bytes (claudeshorts/ingest/fetchers.py).
- Reading-time-aware slide pacing: slides now hold long enough to read their
  text (renderer/lib/timeline.mjs + render.mjs + config/settings.yaml) instead
  of a fixed 4s. Fixes "text scrolls too fast."
- Fixed macOS/Linux dashboard launcher Python/venv selection issue.
