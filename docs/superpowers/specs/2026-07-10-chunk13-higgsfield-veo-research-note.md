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

## Addendum (2026-07-10): the user's existing Google AI Pro subscription

The user already pays for **Google AI Pro** ($20/mo) and asked whether
that removes the cost problem above. It doesn't fully, but it changes the
picture:

- **Pro's Veo access is app/UI-quota, not API credit.** Google AI Pro
  gives roughly **3 Veo 3 Fast generations/day in the Gemini app**, or
  access governed by **~1,000 monthly AI credits shared across Google
  Flow/Whisk** (Ultra: ~5/day in Gemini, ~12,500 monthly Flow credits —
  order-of-magnitude over 100 Veo-3-quality clips/month). This quota is
  **not** the same thing as free Vertex AI API calls — the pay-per-second
  API pricing in this note's Cost Analysis section applies regardless of
  having a Pro/Ultra subscription; the subscription's Veo access lives
  only inside Google's own **Flow** web app (`labs.google/fx/tools/flow`)
  and the Gemini app, both human-facing UIs with no official API tied to
  the subscription tier.
- **This is exactly what chunk 11's browser-profile pattern is for.**
  Flow is a normal logged-in web app; third-party tools already exist
  that batch-automate it via browser extensions (precedent found during
  this research), confirming the approach is viable. A
  `VideoClipProvider` implementation could drive Flow through a Playwright
  profile session (chunk 11's `session.py`/`errors.py`/`wait.py`
  scaffolding, same shape as the browser-based publish provider) instead
  of calling the paid Vertex AI API — using the subscription's included
  quota at **zero marginal cost**, bounded by Pro's daily/monthly limits.
- **This does not solve the volume problem.** ~3-5 Veo clips/day (Pro) or
  ~100/month (Ultra, via Flow credits) is nowhere near
  `posts_per_day: 3` x ~5 slides/post x 30 days (~450 clips/month) needed
  for every slide of every post to have a generated clip. It *does*
  comfortably cover the "opt-in for select content only" usage this
  note already recommended — e.g. one hero clip per top post per day, or
  per week.

**Updated recommendation:** when the user is ready to proceed (still not
this chunk), prefer a `flow_browser` `VideoClipProvider` implementation
(reusing chunk 11's browser-profile plumbing against the subscription's
included quota) as the first, zero-marginal-cost option, with a
Vertex-AI-API-backed `veo_api` implementation as a fallback/scale-up path
only if usage ever needs to exceed the subscription's daily/monthly
limits. Both are real options now, upgraded from "implement later" to
"cheaper path identified" — but still deferred, since it's still new
code needing the user's go-ahead on scope.

## Out of scope for this chunk

No code, no plan document, no API keys obtained, no Flow automation
built — per the user's confirmed "research now" posture. Revisit only
when the user decides to proceed, and treat that as its own new
chunk/spec cycle rather than retroactively expanding this note.

## Addendum (research deep-dive on flow_browser automation)

Follow-up research specifically on the `flow_browser` idea floated in the
addendum above, with real web evidence rather than assumption. Same "research
now" posture — no code touched.

### 1. Technical feasibility

There **is** real-world precedent — this isn't speculative. Multiple Chrome
extensions exist today purpose-built to batch-automate Google Flow: "VEO
Automation," "Flow Automation," "Auto Flow Generator," "AutoFlow," plus at
least two public GitHub repos (`trgkyle/veo-automation-user-guide`,
`Shivanshu85/Google-Flow-Automation`) documenting the pattern — queue
hundreds of prompts from a spreadsheet, submit N concurrently, poll for
completion, auto-download. So driving Flow's UI programmatically is a solved
problem in the wild.

The important nuance is **how** they solve it, and it's not the chunk-11
pattern. These are all **Chrome extensions running inside a normal, real
Chrome session** (content scripts clicking real DOM), not headless
Playwright/Selenium driving a detached browser. That distinction matters:
one freelance job posting found during this research (Upwork, March 2026,
"Fix Playwright Automation for Google Flow AI Video Generator") describes
exactly the chunk-11-style approach failing — image generation worked but
**video generation specifically broke**, with the poster's own diagnosis
being that Flow's prompt editor is a Slate.js rich-text component (not a
plain `<textarea>`, so naive `fill()` calls don't work reliably) and that
Google "may be detecting headless browsers and blocking the request." That
is a direct, named failure mode for the exact approach this note proposed
(chunk 11's `session.py`/`errors.py`/`wait.py` scaffolding is built around
Playwright, effectively meaning headed-but-automated or headless — both are
in the risk zone these reports describe).

Even the working extension-based tools acknowledge the platform pushes
back under sustained automated use: the `veo-automation-user-guide` repo has
a troubleshooting section for an **"Unusual Activity / Verification Error"**
and advises users to test whether their account is flagged by generating a
clip manually — i.e. Google's abuse detection does trigger on these tools in
practice, it just doesn't always block them outright. Mitigations described
(randomized delays, capped concurrency, avoiding "peak hours") are the same
category of workaround as any anti-bot evasion — they reduce detection odds,
they don't eliminate the risk.

**Bottom line on feasibility:** batch UI automation of Flow is demonstrably
possible, but the working examples in the wild use a different technical
approach (extension-in-real-browser) than what chunk 11 built, video
generation is the specific mode reported to break under a from-scratch
Playwright approach, and account-level "unusual activity" flags are a known,
acknowledged occurrence even for the tools that do work.

### 2. ToS / account-risk considerations

This is the part worth being direct about rather than waving through.

Google's general Terms of Service prohibit accessing or using its services
"through the use of any automated means (such as robots, spiders or
scrapers)" without explicit permission, and the Gemini API's own Prohibited
Use Policy and abuse-monitoring docs describe active, ongoing automated
detection of misuse, with enforcement escalating from usage restrictions up
to **closing the Google account entirely** for serious or repeated
violations. Flow sits on the consumer Gemini/Google AI Pro side of that
line, not a developer API key — meaning the account at risk is the user's
**personal Google account** (the same one likely tied to Gmail, Drive,
possibly the browser-profile publishing work from chunk 11), not an
isolated, disposable API credential.

That's the real risk-shape difference from the Veo API path: a suspended or
restricted Vertex AI API key is a billing/access inconvenience you can
recreate. A flagged or suspended personal Google account for "automated
means" use is a much higher blast radius, and it's the exact behavior
pattern (recurring, scheduled, unattended, multi-clip-per-run) that a daily
content pipeline would produce — this is not a one-off manual convenience
script, it's sustained automation against a ToS clause that names automation
specifically. Being honest: this is a real risk the user should weigh, not
one to rubber-stamp away because third parties currently get away with it.
Extensions doing this today are operating in a gray zone that Google's own
enforcement docs say it actively monitors for — "other people haven't been
banned yet" is not the same as "this is compliant."

### 3. Updated pricing/quota check

Both numbers in this note have moved since it was written; corrections below.

- **Veo API pricing**: the previous $0.15–0.40/sec range undersold how cheap
  the low end has gotten and slightly overstated the low end's floor. Current
  figures found: **Lite ~$0.03–0.05/sec** (720p, no audio), **Fast
  ~$0.10–0.15/sec**, **Standard/Quality ~$0.20–0.40/sec**, with a 4K premium
  tier now up to **$0.30–0.60/sec**. The original note's cost-analysis math
  (using $0.15/sec Fast) still holds as a reasonable planning number, but
  Fast can run as low as $0.10/sec, making a small opt-in budget cheaper than
  the note implied.
- **Google AI Pro/Ultra Flow quota**: this is the bigger correction. The
  previous addendum's "~3 Veo Fast generations/day" framing is **stale** —
  Google has since moved Flow to a **monthly credit pool** instead of a daily
  allowance: **Pro ($19.99/mo) = 1,000 Flow credits/month**, **Ultra
  ($99.99/mo... now listed as $100/mo tier) = 10,000/month**, and a higher
  **$200/mo Ultra tier = 25,000/month**. Veo 3.1 Fast costs **20 credits/clip**
  on Pro (10 credits/clip on Ultra), which works out to **~50 Fast clips per
  month on Pro** (not ~90/month as the old "3/day" framing implied) and
  **~500–2,500/month on Ultra** depending on tier. Free (non-subscriber)
  accounts separately get 50 Flow credits/day that reset on first use and do
  not roll over — irrelevant here since the user already pays for Pro.
  Net effect: the subscription's *usable* quota for this use case is somewhat
  **smaller** than the last addendum assumed, but still comfortably covers a
  low-volume opt-in use case (a handful of hero clips a month), just not
  meaningfully more than that.

### 4. Recommendation

**(b) — skip Flow browser automation, use the paid Vertex AI Veo API with a
small opt-in budget (e.g. one hero clip per top post per week), and hold off
on `flow_browser` entirely rather than prototype it.**

Reasoning:

- The volume this note has always recommended as sane (a handful of hero
  clips per week, not per-slide-per-post) is **cheap enough on the metered
  API** that the "free via subscription" appeal of `flow_browser` mostly
  evaporates. One 8-second Fast clip at $0.10–0.15/sec is roughly $0.80–1.20;
  four a month is under $5. That's not a budget decision worth risking a
  personal Google account over.
- The technical case for `flow_browser` is weaker than the prior addendum
  assumed: the working real-world examples use a different automation
  technique (browser extension in a live session) than what chunk 11 built,
  and the one concrete report of someone trying the chunk-11-style approach
  found video generation specifically breaking, with headless-detection as
  the suspected cause.
- The account-risk asymmetry is the deciding factor: the Veo API path risks
  a disposable, recreatable API credential; the Flow path risks the user's
  actual Google account, on a ToS clause that explicitly names automated
  access, for a workload (recurring, scheduled, multi-clip-per-run) that is
  the textbook shape of what that clause is written to catch.
- If the user later wants literally zero marginal cost and is comfortable
  eating the account risk knowingly, this is revisitable — but that should
  be an explicit, informed decision at that time, not a default path taken
  because it looked cheaper on paper.

This doesn't change the note's core `VideoClipProvider` integration
shape — a `veo_api` implementation slots into the same abstraction already
described above (`generate_clip(prompt, duration) -> Path`, opt-in,
defaulting to off, existing static-template rendering untouched for
everyone else). It just settles which concrete implementation to build
first, whenever this chunk is picked back up: `veo_api`, not `flow_browser`.
