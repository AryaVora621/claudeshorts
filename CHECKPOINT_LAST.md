# CHECKPOINT / RESUME REPORT - 2026-07-10 (goal.md platform rebuild — planning phase, update 2)

Agent: Claude (Sonnet 5), branch `feature/carousel-wider-topics`.

## Status: 10 of 14 chunks fully speced + planned (docs only, no implementation yet)

Chunks 7-10 landed since the last checkpoint entry below:
7. LLM provider abstraction — `docs/superpowers/specs/2026-07-10-chunk7-llm-provider-design.md` + plan (`LLMProvider` Protocol; `claude_cli`/`api` moved verbatim; one `OpenAICompatibleProvider` class registered twice as `local`/`openai_compat`, covering Ollama/LM Studio/vLLM and OpenRouter/NVIDIA/Gemini/OpenAI without per-vendor code)
8. More video/renderer styles — `docs/superpowers/specs/2026-07-10-chunk8-video-styles-design.md` + plan (deterministic brand-color pinning by topic keyword — e.g. green for Nvidia, orange for Anthropic — plus 2 new layout templates, `editorial` and `breaking`, alongside today's `slideshow`; layout choice is config-driven keyword rules, not a new LLM field)
9. Remotion research note (chunk originally called "Contexto" — a mishearing the user corrected to Remotion) — `docs/superpowers/specs/2026-07-10-chunk9-remotion-research-note.md`; recommendation: do not migrate the current Playwright+FFmpeg renderer to Remotion now, no clear win and real migration cost; revisit only if a concrete pain point shows up
10. Publishing plugins + multi-channel posting — `docs/superpowers/specs/2026-07-10-chunk10-publishing-plugins-design.md` + plan (`PublishProvider` Protocol; `FolderExportProvider` = today's assisted export, channel-scoped; 3 credential-gated API stub providers for YouTube/TikTok/Instagram, real network calls deferred to a final human-required task; full multi-channel data model built now — `channels` table, `posts.channel_id`, deterministic `select_channel` routing — even though only 1 channel exists today)

**Real gap found while planning chunk 10:** this repo has **no `tests/`
directory at all** yet — every prior chunk's plan (1-9) that said "extend
existing test file X" was actually describing a file that doesn't exist.
Not a blocker (TDD steps create new files regardless), but whoever
executes chunk 1's plan first will need to also create `tests/conftest.py`
with a DB fixture — chunk 10's plan does this defensively (checks for it,
creates if absent) and future chunk plans should do the same rather than
assuming it exists.

## Status (original entry): 6 of 14 chunks fully speced + planned (docs only, no implementation yet)

User's goal.md describes a full platform rebuild (plugin providers, job
queue, service layer, REST API, Telegram bot, scheduling, multi-channel
publishing, Raspberry Pi deployment). Decomposed into 14 chunks (see
`TASK_QUEUE.md` and this session's task list), human-required chunks
(logins/API keys) pushed to the end per user instruction. Current /goal:
"continue working and chunking out plans for this large project, pause
only when needed to ask user or planning is done" — confirmed scope is
**planning** (spec + plan docs), not implementation, until told otherwise.

A cron job (`continue working` every 10 min) is active in this session to
keep this loop going; each firing should pick up the next pending chunk.

### Real infra changes made (not just docs)
- Paused Supabase project `adhdsat` (rhhpshsyrvckouqtyeov) — unrelated to
  this project, paused per user request.
- Created new Supabase project **`claudeshorts`** (id `nddlutmilajkqtoygmfi`,
  region `us-east-1`, free tier, $0/month) — this is the target datastore
  for chunk 1's migration once implemented.

### Chunks done (spec + plan committed, no code written yet)
1. Supabase schema + migrate off SQLite — `docs/superpowers/specs/2026-07-10-chunk1-supabase-migration-design.md` + plan
2. Job queue + state machine — `docs/superpowers/specs/2026-07-10-chunk2-job-queue-design.md` + plan
3. Service layer extraction — `docs/superpowers/specs/2026-07-10-chunk3-service-layer-design.md` + plan
4. REST API over services — `docs/superpowers/specs/2026-07-10-chunk4-rest-api-design.md` + plan
5. Scheduling engine — `docs/superpowers/specs/2026-07-10-chunk5-scheduling-engine-design.md` + plan (self-contained recurring scheduler; weekly report has an honest "pending Playwright analytics" placeholder, real cross-platform engagement deferred to chunk 11 per user's choice of Playwright scraping over platform APIs)
6. Structured logging overhaul — `docs/superpowers/specs/2026-07-10-chunk6-structured-logging-design.md` + plan

### Next action (superseded — see chunks 7-10 note above)
Chunk 11: browser-automation profile system + Playwright-based analytics
scraper (feeds chunk 5's weekly report). Then chunks 12-14 (Telegram bot,
Higgsfield/Veo, additional LLM keys) — these need API keys/logins from the
user, per their explicit "leave human-required tasks for last" instruction.

### Human decisions needed
None blocking right now — next chunks proceed with reasonable defaults,
flagging real decisions via AskUserQuestion as they come up (this has been
the working pattern: DB access approach, data migration scope, cancel/pause
depth, API auth, etc., each confirmed before writing the spec).

---

# CHECKPOINT / RESUME REPORT - 2026-06-10 (launcher PATH fix)

Agent: Codex.

## Status: fixed locally, ready for user test
The macOS/kitty launcher failure was reproduced with a minimal Finder-like PATH:

```text
PATH=/usr/bin:/bin:/usr/sbin:/sbin ./start-dashboard.sh
```

Root cause: Python 3.13 was installed in normal macOS locations
(`/opt/homebrew/bin`, `/usr/local/bin`, and the python.org framework path), but
the launcher only checked command names visible through the inherited PATH. Some
double-click or kitty launches do not load the user's shell profile, so the
launcher reported that Python 3.11+ was missing even though it was installed.

## What changed
- `start-dashboard.sh` now prepends standard macOS local install paths to PATH
  before probing tools.
- `find_python()` now also checks `.venv/bin/python`, Homebrew Python paths,
  `/usr/local/bin` Python paths, and python.org framework paths by absolute path.

## Verified
- `bash -n start-dashboard.command start-dashboard.sh`
- Minimal-PATH `./start-dashboard.sh` on port 8765: found
  `/opt/homebrew/bin/python3.13`, started the dashboard, and served `/` with
  HTTP 200. The test server was stopped cleanly.
- Minimal-PATH `./start-dashboard.command` on port 8766: found
  `/opt/homebrew/bin/python3.13`, started the dashboard, and served `/` with
  HTTP 200. The test server was stopped cleanly.

## Next action
User can run `./start-dashboard.command` or double-click it and test the
dashboard normally.

## Human decisions needed
None for this launcher fix.

---

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
