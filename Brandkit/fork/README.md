# fork.ai — Brand Kit

AI & tech news, forked daily — short videos on YouTube/TikTok/Instagram.
A text version (newsletter) is a future plan, not built yet — the bios
allude to "more coming" without promising something that doesn't exist.

## Visual identity (v4 — flat, no glow, 4-prong fork)

v1 (bracket-corner terminal frame) and v2 (neon glow git-fork icon, branch
metaphor) both read as generic "AI-generated" aesthetic — heavy radial
glows and gradients are a visual cliché at this point, not a brand. v3
flattened the color but kept a 3-prong branch/git-fork shape. v4 (current)
switches to a literal 4-prong dinner-fork silhouette — clearer pun on the
name, reads better at small sizes, single flat color, no glow/gradient:

- Background: `#111111` (flat near-black, no gradient)
- Primary accent: `#A855F7` (purple) — flat fill, no glow
- Text/highlight: `#F5F0FF`
- Font: JetBrains Mono (monospace, terminal feel, but bold/blocky not neon)
- Mark: a flat 4-prong fork silhouette (four tines, a neck bar, a handle) —
  literal, single-color, geometric. No gradients, no blur, no dual-tone
  accents.

## Assets

- `logo_1024x1024.png` — square profile picture (all platforms)
- `banner_2560x1440.png` — YouTube channel art (safe zone: center ~1546x423)
- `highlight-cover_400x400.png` — transparent PNG of the mark alone, for
  Instagram Story highlight covers (Instagram applies its own circular crop)
- `logo.html` / `banner.html` / `highlight-cover.html` — source, re-renderable
  via Playwright

To regenerate: copy a `shoot`-style script into `renderer/` (needs its
`node_modules/playwright`), point `outDir` at this folder, run with
`node <script>.mjs` from inside `renderer/`.

## Handle: @fork.ai

Brand name and handle are now the same thing: **fork.ai**. Verified live via
browser (2026-07-11):

| Platform | Handle | Status |
|---|---|---|
| Instagram | @fork.ai | confirmed free |
| YouTube | @fork.ai | confirmed free (real 404, not a shell page) |
| TikTok | @fork.ai | not checked — TikTok was geoblocked/glitching during the check; verify manually at `tiktok.com/@fork.ai` |

### How we got here

Research on handle length/phonetics pointed at short, dev-culture-
recognizable, keyword-bearing handles over the original literal
`@terminalbrief` (13 chars, no explicit niche keyword). Iterated through
`ai.relay` → `sudo.relay`/`root.relay`/etc. → single-word `.ai` handles,
live-checking each candidate directly in a browser (actual profile or 404
page, not a guess). Confirmed taken along the way: `ai.relay`, `ai.wire`,
`dailyrelay`, `relay.ai`, `sudo.ai`, `echo.ai`, `wire.ai`, `byte.ai`,
`ping.ai`, `patch.ai`, `boot.ai`, `loop.ai`, `daemon.ai`, `trace.ai`,
`diff.ai`, `pipe.ai`, `init.ai`, `ship.ai`, `core.ai`, `beam.ai`, `sync.ai`,
`node.ai`, `logs.ai` (a near-identical concept already live there),
`kernel.ai`. Confirmed free: `grep.ai`, `cron.ai`, `fork.ai`, `yaml.ai` —
user picked **`fork.ai`**.

## Bios

Newsletter is alluded to lightly (future plan), not presented as a live
feature — no bio link promises a signup that doesn't exist yet.

**YouTube (About)**
> fork.ai — AI & tech news, forked daily.
> Short, no fluff. A text version is in the works.
> `$ ai_news --daily --no-fluff`

**TikTok**
> AI & tech news, forked daily
> text version coming eventually
> new drop every day

**Instagram**
> fork.ai
> AI & tech news, forked daily.
> more formats coming soon

## What's still needed to actually launch (not generated — needs you)

**YouTube**
- Google account for the channel (dedicated one recommended)
- Claim handle `@fork.ai` immediately on channel creation — first-come
- Paste the bio above into About, add channel keywords (ai news, tech news,
  daily briefing)
- Phone verification (unlocks custom thumbnails, longer uploads)
- Default upload category (News & Politics or Science & Technology), 2FA

**Instagram**
- Set account type to Professional (Creator), not Personal
- Category tag (e.g. "Digital creator" or "News & media")
- One bio link — straight to YouTube for now (no newsletter to link yet)
- Story highlight covers: use `highlight-cover_400x400.png` (transparent,
  crops into a circle automatically)
- 2FA

**Newsletter — future plan, not started**
Bios allude to "more formats coming" so this isn't a promise made in a
vacuum, but nothing is built or decided yet. When it's time: pick a sender
(Substack/beehiiv/self-hosted), decide cadence, and note that the
claudeshorts renderer already generates the daily slide copy the newsletter
could reuse instead of writing fresh copy. Not a current task.

**Both**
- Recovery email/phone owner decided up front for both accounts
- Consistent `@fork.ai` tag used everywhere for cross-mentions

## Status

Logo, banner, and highlight cover rendered (v4, flat 4-prong fork, single
bullet). Bios updated to only vaguely allude to a future text format, not
present a live newsletter. Newsletter platform itself is not set up and not
a current task — that's a real account-creation step like YouTube/
Instagram, not something a mockup can stand in for.
