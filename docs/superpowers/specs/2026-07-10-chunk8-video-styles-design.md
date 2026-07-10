# Chunk 8: More video/renderer styles

## Context

Eighth of 14 chunks rebuilding claudeshorts per `goal.md` (see `TASK_QUEUE.md`
/ session task list). This chunk is pure code — no human-required
credentials — so it isn't deferred to the end.

## Current state

Every post renders through exactly one HTML template,
`renderer/templates/slideshow.html`: a dark neon-gradient layout with
animated blobs, staggered bullet entrance, and a kicker/headline/bullets
stage. Colors are driven by a per-post `theme` object
(`primary`/`secondary`/`accent`/`mood`) that Claude freely invents per
generation to match "the SUBJECT of the news" (`generate/schema.py`'s
`POST_TOOL.theme`, prompted in `generate/generator.py`) — so the same
subject (e.g. Nvidia) can get a different green every time, and there is
no layout variation at all: `renderer/render.mjs`'s `TEMPLATE` constant is
a single hardcoded path.

## Decision (confirmed with user)

Two independent, additive mechanisms, both deterministic (config-driven,
not further LLM prompting) so behavior is consistent, testable, and free:

1. **Brand color pinning.** A new `config/settings.yaml` `styles:
   brand_colors:` map from lowercase subject keyword (e.g. `"nvidia"`) to a
   fixed `{primary, secondary, accent, mood}` palette. After Claude
   generates a post, a pure post-processing step matches `theme.subject`
   (case-insensitive substring match) against the known keywords; on a
   match, the pinned palette overrides Claude's freeform colors. No match
   leaves Claude's generated colors untouched. This is what the user meant
   by "per profile theme but semi-optimized per post/topic (green for
   Nvidia, orange for Anthropic, etc.)" — consistent, recognizable colors
   per company without hand-authoring every possible subject.
2. **Layout templates.** Two new HTML templates alongside today's
   `slideshow.html` (renamed conceptually to "the default layout", kept as
   the fallback): an **editorial** layout (calmer — generous whitespace,
   slower fades, muted single-line separators; for analysis/deep-dive
   posts) and a **breaking** layout (urgent — bold condensed headline,
   pulsing accent bar, faster stagger, ticker-style banner; for
   launch/release/announcement posts). Layout choice is a config-driven
   keyword-rule lookup against the item, mirroring the brand-color
   mechanism's determinism, with `slideshow` as the always-available
   default.

Both mechanisms are pure functions over data already available at
generation time (the item's title/tags/source and Claude's own
`theme.subject`) — no new LLM calls, no new required schema fields, so
existing generated-but-not-yet-rendered posts are unaffected until
regenerated.

## Architecture

### `claudeshorts/generate/style_rules.py` (new)

```python
def pin_brand_colors(theme: dict, brand_colors: dict) -> dict:
    """Return theme with primary/secondary/accent/mood overridden if
    theme['subject'] case-insensitively contains a known brand keyword;
    otherwise theme is returned unchanged. Longest keyword match wins so
    e.g. 'google deepmind' doesn't accidentally match a shorter unrelated
    key before a more specific one."""

def select_layout(item: dict, layout_rules: dict, default_layout: str) -> str:
    """Match item['title']/item['summary'] (case-insensitive substring)
    against each layout's keyword list in layout_rules; first layout whose
    keyword list has a hit wins, in the dict's insertion order. No match ->
    default_layout."""
```

Both are pure, no I/O, no LLM calls — trivially unit-testable.

### `config/settings.yaml` additions

```yaml
styles:
  brand_colors:
    nvidia:     {primary: "#76B900", secondary: "#0A0A0A", accent: "#FFFFFF", mood: dark}
    anthropic:  {primary: "#D97757", secondary: "#F5F0E8", accent: "#1A1A1A", mood: light}
    openai:     {primary: "#10A37F", secondary: "#0A0A0A", accent: "#FFFFFF", mood: dark}
    google:     {primary: "#4285F4", secondary: "#0A0A0A", accent: "#FFFFFF", mood: dark}
    meta:       {primary: "#0668E1", secondary: "#0A0A0A", accent: "#FFFFFF", mood: dark}
    microsoft:  {primary: "#00A4EF", secondary: "#0A0A0A", accent: "#FFFFFF", mood: dark}
  layout_rules:
    breaking:  ["launch", "launches", "release", "releases", "announces", "unveils"]
    editorial: ["analysis", "opinion", "deep dive", "explainer", "why "]
  default_layout: slideshow
```

`brand_colors`/`layout_rules` are intentionally short starter lists — real
usage will grow them; unmatched subjects/items are not an error, they just
fall through to Claude's own colors and `slideshow`.

### Call site: `claudeshorts/generate/runner.py`

Where `generate_post`'s result is consumed (today around line 42, where
`theme=data["theme"]` is passed to post creation), add:

```python
from . import style_rules
...
cfg = settings().get("styles", {})
data["theme"] = style_rules.pin_brand_colors(data["theme"], cfg.get("brand_colors", {}))
layout = style_rules.select_layout(item, cfg.get("layout_rules", {}), cfg.get("default_layout", "slideshow"))
```
`layout` is then passed through to `posts.create_post(..., layout=layout)`.

### Storage: `store/db.py` / `store/posts.py`

New column `posts.layout TEXT` (default `'slideshow'`), added via the
existing `_apply_migrations()` pattern (same style as prior
`("posts", "theme_json", "TEXT")` entries). `create_post` gains a
`layout: str = "slideshow"` parameter; the row-to-dict mapper returns it
as `d["layout"]`.

### Render path: `claudeshorts/render/bridge.py` / `renderer/render.mjs`

`bridge.py`'s spec assembly (where `"theme": post.get("theme") or {}` is
built, `render/bridge.py:102`) adds `"layout": post.get("layout") or
"slideshow"` to the same spec dict.

`render.mjs`'s hardcoded `TEMPLATE` constant becomes a lookup against an
explicit allowlist (defense in depth — `layout` reaches this point through
several config/LLM-influenced hops, not raw user input, but a wrong or
unexpected string must never become a filesystem path):

```js
const LAYOUTS = { slideshow: "slideshow.html", editorial: "editorial.html", breaking: "breaking.html" };
const templateFile = LAYOUTS[spec.layout] || LAYOUTS.slideshow;
const TEMPLATE = join(HERE, "templates", templateFile);
```

### New templates

`renderer/templates/editorial.html` and `renderer/templates/breaking.html`
each implement the exact same JS contract `slideshow.html` already does
(`window.__init(spec) -> slideCount`, `window.__render(i, localMs,
globalMs)`) so `render.mjs`'s Playwright-driving loop needs zero changes
beyond the template-path lookup above. Both consume the same `theme`
(primary/secondary/accent/mood) and `channel` (handle/logo/name) spec
fields as `slideshow.html` — no new spec fields, so brand-color pinning
applies uniformly regardless of which layout a post uses.

- **editorial**: generous whitespace, no animated background blobs (a
  single soft static gradient instead — cheaper to render too), slower
  600ms->900ms fade timings, thinner typographic weight, subtle top-rule
  divider instead of a glowing kicker dot.
- **breaking**: bold condensed headline weight, a pulsing top ticker
  banner reading the kicker text, faster 300ms->450ms stagger, a
  higher-contrast/more saturated background treatment (reuses the same
  blob mechanic as `slideshow.html` but larger/faster motion).

## Out of scope for this chunk

- LLM-driven layout selection (Claude choosing/suggesting a layout) — the
  decision was explicitly for config-driven determinism, not a new schema
  field or prompt change.
- A dashboard UI for editing `brand_colors`/`layout_rules` — these are
  `config/settings.yaml` edits for now, consistent with how every other
  tunable in this codebase works.
- Automated visual regression testing of the two new templates (no visual
  diffing harness exists in this codebase) — verified instead by a human
  running one real render per new layout, same as prior template changes
  in this project's history (e.g. the outro-slide work).
- A 4th+ layout — two is the scope confirmed with the user; more can be
  added later following the same allowlist pattern.

## Testing

`tests/generate/test_style_rules.py` — brand color pin: exact match,
case-insensitive match, substring match within a longer subject string,
longest-match-wins when two keywords could both match, no match leaves
theme unchanged. Layout rule: first-match-wins in insertion order, no
match falls back to `default_layout`, empty `layout_rules` always returns
default.

`tests/store/test_posts.py` (existing file, extended) — `layout` persists
through `create_post`/round-trip read, defaults to `"slideshow"` when
omitted.

`tests/render/test_bridge.py` (existing file, extended) — spec dict
includes `layout`, defaulting to `"slideshow"` when the post has none.

Manual (documented, not automated): after implementation, render one real
post through each of the 3 layouts and visually confirm output — same
verification approach used for this project's prior renderer changes.
