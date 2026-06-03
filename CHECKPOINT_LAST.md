# CHECKPOINT / RESUME REPORT - 2026-06-02 (carousel deck in dashboard)

Agent: Claude (Opus 4.8), branch `feature/carousel-wider-topics`.

## Status: DONE + verified live (UNCOMMITTED working-tree changes)
The carousel deck now appears in the dashboard. It was already exported to
`publish/<platform>/` but was never displayed: the `/media` route only served
`video.mp4`/`thumb.png` and no template rendered the slides. Finished end to end
and verified live with Playwright. Nothing committed yet.

## What was built this session
- `claudeshorts/dashboard/app.py`
  - `/media/{post_id}/{name:path}` now also serves `slides/slide_NN.png`, gated
    by `_SLIDE_RE = ^slides/slide_\d{2,}\.png$` (blocks path traversal); the
    earlier exact-name allowlist stays for video/thumb. `_media_path` also falls
    back to `renders/post_<id>/` after the review bundle.
  - New `GET /posts/{id}/carousel` -> full-size deck page.
  - Review + Posts routes pass per-post deck info (`decks`).
- `claudeshorts/review/queue.py` — new `carousel_slides(post_id)` -> sorted slide
  filenames (review bundle first, then render dir; [] for pre-carousel posts).
- Templates: new `_carousel.html` (reusable swipeable deck; `pid`, `slides`,
  optional `variant="inline"`) and `carousel.html` (standalone page). `review.html`
  embeds the deck under the video; `posts.html` adds a "Carousel (N)" link;
  `base.html` gained a `{% block scripts %}`.
- `static/carousel.js` — prev/next, click-drag, arrow keys, live `n/total`
  counter over a native CSS scroll-snap track (progressive enhancement).
- `static/app.css` — `.carousel*` component + `.deck-label`/`.deck-stage`.

## Verified (this session)
- TestClient: `/review` (markup present), `/posts`, `/posts/10/carousel` all 200;
  `/media/10/slides/slide_01.png` -> 200 image/png (647 KB); `/media/10/video.mp4`
  -> 200; traversal `slides/../../../etc/passwd` -> 404; `slide_99.png` -> 404;
  Posts page contains the carousel link. Decks exist for posts 4/5/10/11/12.
- Playwright (live server on :8791): Review cards show video + inline deck;
  `/posts/10/carousel` renders full size; clicking next scrolled exactly one
  slide (scrollLeft 0->428 == clientWidth) and the counter went 1->2 of 5.
- `node --check carousel.js` passed. Test artifacts (screenshots, .playwright-mcp)
  cleaned; test server stopped.

## Also this session: auto-included ending slide
The carousel + jobs dashboard work was committed as `ecdc095`. Then added an
auto-included outro slide (committed separately — see git log):
- `assets/EndingSlide.png` (941x1672 source) is normalized to 1080x1920 and
  appended to every video (held `video.endslide_seconds`, default 2.5s) AND as
  the final carousel still.
- `render/bridge.py::_endslide_path` auto-detects an outro image in `assets/`
  (or honors settings `video.endslide`; `""` disables) and passes an absolute
  path in the render spec. `renderer/render.mjs` normalizes it, extends the
  timeline by one trailing "slide" (keeps audio in sync), fills those frames
  from the image, and copies it as the last `slides/slide_NN.png`.
- Verified live (post 10, real Chromium+ffmpeg): 40.0s->42.5s, +75 frames, last
  video frame = the outro, deck 5->6 stills (slide_06 = branded outro).

## Re-rendered the review queue with the new outro (2026-06-02)
Posts 12, 11, 10, 5 (status `rendered`) re-rendered + re-assembled so the
dashboard decks and videos carry the outro. Verified: review bundles now hold
7/6/6/6 stills, each deck's last still is byte-identical (the same normalized
outro, md5 56e1883c07), videos are 49.9/42.5/42.5/42.2s. Left exported posts
(1, 4) and rejected post 2 untouched so shipped content isn't altered; drafts
(3, 8, 9) were never rendered. (These live in gitignored review/ + renders/, so
nothing to commit.)

## Pushed + LAN dashboard + local-model plan (2026-06-02)
- Pushed `feature/carousel-wider-topics` to origin (commits up to the LAN work).
- LAN-accessible dashboard: `start-dashboard.sh` now binds `${CLAUDESHORTS_HOST:-0.0.0.0}`
  (all interfaces) so other LAN devices can reach the desktop's dashboard; passes
  `--host` to `cli serve` and prints local + auto-detected LAN URLs. Override with
  `CLAUDESHORTS_HOST=127.0.0.1`. Verified: 200 on 127.0.0.1 AND 192.168.1.164.
- Local-model backend: PLAN ONLY, written to `docs/PLAN_local_model.md` (Qwen3-30B-A3B
  GGUF on the P40; fp8 impossible on Pascal -> use Q4/Q5 GGUF via Ollama/llama.cpp;
  new `local` backend reusing JSON-in-prompt + validate_post). Not implemented.

## BLOCKED
- Home server `aiserver@192.168.1.178` unreachable (incomplete ARP from a same-
  subnet machine, 192.168.1.164). User is fixing the Linux box; deferred. The
  server end-to-end test + the local-model build wait on this.

## NEXT (resume here)
1. When the server is back: pull the branch, run the launcher (now LAN-bound),
   do the end-to-end test, then open a PR / merge to main.
2. Local model: get user's calls on the open decisions in `docs/PLAN_local_model.md`
   (Ollama vs llama.cpp, quality bar, quant target), then implement the `local`
   backend.

## Human decisions needed
- The 3 open decisions in `docs/PLAN_local_model.md` (inference server, quality
  trade-off, quant target).
