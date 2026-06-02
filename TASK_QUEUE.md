# Task Queue

## Open
- Batch generation (up to 20): clamp 1-20 + per-post error isolation + a `rich`
  progress bar (per-post + total). NEXT.
- Better near-duplicate dedup for big batches: token-overlap dedup misses the
  same story across outlets (e.g. 3 "Anthropic IPO" items ranked top). Matters
  once batches are 20. Consider tighter/semantic dedup.

## In-Progress
- None.

## Done
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
