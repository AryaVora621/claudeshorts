# Chunk 13: Higgsfield + Google Veo video-gen research note

## Context

Thirteenth of 14 chunks rebuilding claudeshorts per `goal.md`. The user
flagged this early on as "research now, implement later" and explicitly
deferred it to the end, alongside additional LLM API keys (chunk 14) —
both genuinely human-required (real paid API credentials) and lower
priority than the rest of the rebuild. This chunk is research-only, same
posture as chunk 9's Remotion note: no code, no implementation plan.

## What these are

**Higgsfield AI** is a video-generation platform/API (image-to-video and
text-to-video) that itself wraps several underlying models (its own,
plus resold access to Kling, Veo, Sora, etc.) behind one API and a
credit-based pricing system. **Google Veo 3.1** is Google's own
text/image-to-video model, available directly via the Gemini API
(pay-per-second) or through Higgsfield as one of its resold model
options.

**Current pricing (as of this research, July 2026):**
- Veo 3.1 direct via Gemini API: **$0.15/sec (Fast, with audio)** to
  **$0.40/sec (Standard, with audio)**; a Lite 720p no-audio tier runs as
  low as $0.03/sec. An 8-second clip at Standard quality costs about
  $3.20.
- Higgsfield: subscription tiers at $15/$39/$99 per month (credit-based:
  200/1,000/3,000 credits), with Veo 3/3.1 access requiring at least the
  Plus tier — its Starter tier excludes Veo entirely. A single Veo 3
  8-second clip costs ~58 Higgsfield credits (roughly a third of the
  Plus tier's monthly allotment for one clip).

## How this would integrate with claudeshorts

The generation schema (`claudeshorts/generate/schema.py`'s `POST_TOOL`)
already has an unused hook for exactly this: each slide has a
`visual_hint` field (`"description": ...` free-text, populated by Claude
today but never consumed by the renderer). The natural integration point
is: instead of `renderer/templates/*.html`'s CSS gradient-blob background,
a slide's `visual_hint` becomes the prompt sent to a video-gen provider,
and the resulting short clip becomes that slide's background video layer
(the existing headline/bullets/kicker text overlay stays unchanged on
top). This would slot in as a new provider abstraction — a
`VideoClipProvider.generate_clip(prompt: str, duration: float) -> Path`
protocol, mirroring the `LLMProvider` (chunk 7) and `PublishProvider`
(chunk 10) patterns already established in this rebuild — selected
per-channel or per-post as an opt-in visual upgrade over the default
free static-template rendering, never replacing it.

## Cost analysis (the real blocker)

Today's pipeline costs effectively nothing per video beyond Claude
Pro/Max subscription usage and local compute (Playwright + FFmpeg,
already free). Adding AI-generated video clips is a real, recurring
per-video dollar cost that scales with output volume:

- A typical post has 3-7 slides (`schema.py`'s `minItems`/`maxItems`),
  each held 4-8 seconds (`video.seconds_per_slide`/
  `max_seconds_per_slide`).
- At Veo 3.1 Fast pricing (~$0.15/sec) and ~5 slides averaging 5s each:
  **~$3.75 per video** in clip-generation cost alone.
- At `posts_per_day: 3` (current default), that's **~$11/day, ~$340/month**
  just for video clips — before any Higgsfield subscription markup, and
  scaling linearly with `posts_per_day` or slide count.
- Higgsfield's credit system doesn't obviously improve this: Plus tier
  ($39/mo, 1,000 credits) covers roughly 17 Veo-3-quality 8s clips before
  running out — nowhere near 3 posts/day x 5 slides x 30 days.

This is the central finding: **AI video clips are not a marginal cost
add-on the way Remotion (chunk 9) would have been** — they represent a
real, ongoing operating expense that must be a deliberate budget decision,
not something wired in as a default.

## Recommendation

**Research now, implement later — confirmed as the right call.** The
integration point is clean (a new provider abstraction feeding the
existing, currently-unused `visual_hint` field) and could be built the
same way LLM/publish providers were, whenever the user decides the
per-video cost is worth it for some subset of content (e.g. only the
channel's top-performing post each week, or only launch-day "breaking"
layout posts where higher production value matters most). Suggested
follow-up chunk, if/when the user wants to proceed: a `VideoClipProvider`
protocol + one concrete `veo_api` implementation (direct Gemini API,
simpler pricing/access than Higgsfield's resold/credit model) + a
per-channel or per-post opt-in flag defaulting to off, with the existing
static-template rendering remaining the zero-cost default for everyone
else.

## Out of scope for this chunk

No code, no plan document, no API keys obtained — per the user's
confirmed "research now" posture. Revisit only when the user decides the
per-video cost is worth spending against, and treat that as its own new
chunk/spec cycle rather than retroactively expanding this note.
