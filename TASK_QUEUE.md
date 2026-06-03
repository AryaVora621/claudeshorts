# Task Queue

## Open
- Test the `feature/carousel-wider-topics` branch on the HOME SERVER (pull,
  ingest, generate --limit 20, render, eyeball video + carousel), then open a
  PR / merge to main. (User testing this next.)
- DEPRIORITIZED — cross-outlet duplicate stories: "some duplicates are fine"
  (user). Investigation notes in CHECKPOINT_LAST.md (IDF-weighted shared-token
  approach; RTX-Spark false-merge risk). Revisit only if it becomes annoying.
- Optional: parallelize batch generation (run a few claude CLI calls at once).
- Optional: Reddit OAuth so the disabled reddit sources work again.

## In-Progress
- [IN_PROGRESS Claude/Opus] Live jobs dashboard: percent bars (phase + per-item),
  clickable job history that survives restarts (new `jobs` SQLite table),
  embedded live terminal in the dashboard. Frontend + read-only progress
  instrumentation only (no stop/cancel, no change to what jobs do). See PLAN.md.

## Done
- Auto-included ending slide: a pre-made outro image (auto-detected from
  `assets/`, e.g. `EndingSlide.png`; override via settings `video.endslide`) is
  normalized to 1080x1920 and appended both to the end of every video (held
  `video.endslide_seconds`, default 2.5s) and as the final carousel swipe. The
  timeline is extended so the audio track stays in sync. Verified on post 10:
  40.0s -> 42.5s video that ends on the outro frame; deck grew 5 -> 6 stills with
  the branded outro last. (`render/bridge.py::_endslide_path`, `renderer/render.mjs`.)
- Carousel deck preview in the dashboard: slide stills now show on the dashboard.
  `/media/{id}/slides/slide_NN.png` serves the stills (path-validated; traversal
  blocked), `review/queue.py::carousel_slides` lists a post's deck, the Review
  card shows a swipeable deck under the video, a new `/posts/{id}/carousel` page
  shows it full-size, and the Posts table links "Carousel (N)". New
  `templates/_carousel.html` + `carousel.html`, `static/carousel.js` (buttons +
  drag + arrow keys + live counter), CSS. Verified live (Playwright): inline +
  standalone render, next advances exactly one slide (0->428px, counter 1->2),
  real PNG bytes served, traversal/missing-slide -> 404.
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
