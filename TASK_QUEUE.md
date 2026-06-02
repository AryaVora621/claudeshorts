# Task Queue

## Open
- Batch generation (up to 20): clamp 1-20 + per-post error isolation + a `rich`
  progress bar (per-post + total). [deferred behind carousel per user]
- Wider topic range: add diverse tech RSS sources (security, hardware/chips,
  consumer/gadgets/gaming, AI/top-companies) + virality-aware "buzz" scoring in
  selection (today's batches are Hacker-News-dominated). [deferred]

## In-Progress
- None.

## Done
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
