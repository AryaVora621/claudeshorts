# Chunk 9: Remotion — research note

## Context

Ninth of 14 chunks rebuilding claudeshorts per `goal.md`. The user asked
early on to "keep Contexto in mind" as a lighter/lower-priority research
item alongside Higgsfield/Veo (chunk 13); on reaching this chunk, the user
clarified "Contexto" was a mishearing/autocorrect of **Remotion**, the
React-based programmatic video framework. This chunk is research-only —
"research now, implement later," same posture as chunk 13's Higgsfield/Veo
item, and explicitly lower priority than that chunk per the original
ordering decision.

## What Remotion is

Remotion lets you define video content (layouts, animations, timing) as a
React component tree, then renders it to MP4 by driving a headless
Chromium instance frame-by-frame and stitching the captured frames with
FFmpeg. It supports local rendering, self-hosted server rendering, and a
serverless option (Remotion Lambda) for parallel scale-out.

## How this compares to claudeshorts' current renderer

`renderer/render.mjs` already does the conceptually identical thing by
hand: static HTML/CSS/JS templates (`renderer/templates/*.html`, one per
layout as of chunk 8) driven by Playwright at a fixed frame clock, with
frames stitched by FFmpeg via `renderer/lib/ffmpeg.mjs`. The core
mechanism — headless-browser-frame-capture-plus-FFmpeg — is the same
approach Remotion itself uses internally. The real question isn't "does
Remotion do something we can't do," it's "would swapping our hand-rolled
HTML/CSS templates for React components meaningfully improve anything."

**Where Remotion would help:**
- Declarative animation primitives (`interpolate`, `spring`, sequencing
  components) replace this project's hand-written `easeOut`/manual
  `translateY` math in each template — less boilerplate per new layout.
- A built-in Studio UI for live-previewing/scrubbing templates during
  development, which this project has no equivalent of today (verification
  is currently "render the real video and watch it," as chunk 8's plan
  documents).
- A path to Remotion Lambda if render volume ever needs to scale beyond
  one machine — not a current need, but a documented option.

**Where it wouldn't help / adds cost:**
- Licensing: free for individuals and companies with ≤3 employees doing
  commercial work, which covers this project today — but it's a real
  constraint to track if claudeshorts ever grows a team, unlike the
  current from-scratch renderer which has no such ceiling.
- Migration cost: `renderer/render.mjs`'s spec contract
  (`window.__init(spec)` / `window.__render(i, localMs, globalMs)`,
  chunk 8's `LAYOUTS` allowlist) would need to be entirely rebuilt around
  React component composition and Remotion's own CLI/rendering API — a
  non-trivial rewrite of a system that already works, for animation
  ergonomics gains only (no capability the current system structurally
  lacks).
- Raspberry Pi fit: Remotion still shells out to a full headless Chromium
  render exactly like today's Playwright approach — no meaningfully
  different resource profile for the "optimize for RPi from the start"
  goal. It neither helps nor hurts that constraint; it's a wash.
- Node dependency surface grows (Remotion + React + its own CLI) versus
  the current renderer's minimal `playwright` + `ffmpeg` footprint — a
  real cost on a resource-constrained Pi deployment target, however
  modest.

## Recommendation

**Do not migrate now.** The current custom Playwright+FFmpeg renderer
already supports multiple layouts as of chunk 8, works, and has no
Raspberry Pi disadvantage relative to Remotion. Adopting Remotion today
would mean rewriting a working system for animation-authoring convenience
alone, which doesn't clear the bar this project has otherwise held
(YAGNI, avoid speculative rewrites). Revisit this decision only if a
concrete pain point actually shows up in practice — e.g., authoring a 4th+
layout becomes materially painful with hand-written CSS/JS, or render
volume genuinely needs Lambda-style horizontal scale-out. Until then, no
action item beyond this note.

## Out of scope for this chunk

No code changes, no plan document — per the user's confirmed "research
now" posture (matching chunk 13's Higgsfield/Veo treatment), this chunk
produces only this note.
