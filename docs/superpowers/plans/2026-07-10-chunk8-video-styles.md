# Chunk 8: More Video/Renderer Styles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic brand-color pinning and two new selectable renderer layouts (`editorial`, `breaking`) alongside today's `slideshow`, with zero new LLM schema fields or prompt changes.

**Architecture:** A new pure-function module (`generate/style_rules.py`) computes pinned colors and a chosen layout from config + the already-generated post; a new `posts.layout` column carries the choice through storage; `render/bridge.py` and `renderer/render.mjs` add an allowlisted template lookup.

**Tech Stack:** Python 3.11+, existing SQLite/Postgres store layer, Node.js/Playwright renderer (no new dependencies).

## Global Constraints

- No comments explaining *what*, only non-obvious *why*.
- Pure functions only in `style_rules.py` — no I/O, no LLM calls.
- `layout` must go through an explicit allowlist before touching the filesystem (defense in depth).
- Full spec: `docs/superpowers/specs/2026-07-10-chunk8-video-styles-design.md`.

---

## File Structure

- Create: `claudeshorts/generate/style_rules.py`
- Modify: `config/settings.yaml`, `claudeshorts/generate/runner.py`, `claudeshorts/store/db.py`, `claudeshorts/store/posts.py`, `claudeshorts/render/bridge.py`, `renderer/render.mjs`
- Create: `renderer/templates/editorial.html`, `renderer/templates/breaking.html`
- Test: `tests/generate/test_style_rules.py`, extend `tests/store/test_posts.py`, extend `tests/render/test_bridge.py`

---

### Task 1: `style_rules.py` — brand color pinning + layout selection

**Files:**
- Create: `claudeshorts/generate/style_rules.py`
- Test: `tests/generate/test_style_rules.py`

**Interfaces:**
- Produces: `pin_brand_colors(theme: dict, brand_colors: dict) -> dict`, `select_layout(item: dict, layout_rules: dict, default_layout: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# tests/generate/test_style_rules.py
from __future__ import annotations

from claudeshorts.generate.style_rules import pin_brand_colors, select_layout

BRAND_COLORS = {
    "nvidia": {"primary": "#76B900", "secondary": "#0A0A0A", "accent": "#FFFFFF", "mood": "dark"},
    "google": {"primary": "#4285F4", "secondary": "#0A0A0A", "accent": "#FFFFFF", "mood": "dark"},
    "google deepmind": {"primary": "#8E44AD", "secondary": "#0A0A0A", "accent": "#FFFFFF", "mood": "dark"},
}


def _theme(subject: str) -> dict:
    return {"subject": subject, "primary": "#111111", "secondary": "#222222",
            "accent": "#333333", "mood": "light"}


def test_pin_brand_colors_exact_match():
    result = pin_brand_colors(_theme("Nvidia"), BRAND_COLORS)
    assert result["primary"] == "#76B900"
    assert result["mood"] == "dark"


def test_pin_brand_colors_case_insensitive_substring():
    result = pin_brand_colors(_theme("Nvidia's new Blackwell chip"), BRAND_COLORS)
    assert result["primary"] == "#76B900"


def test_pin_brand_colors_longest_match_wins():
    result = pin_brand_colors(_theme("Google DeepMind ships Gemini 4"), BRAND_COLORS)
    assert result["primary"] == "#8E44AD"


def test_pin_brand_colors_no_match_returns_unchanged():
    original = _theme("Some Unknown Startup")
    result = pin_brand_colors(original, BRAND_COLORS)
    assert result == original


def test_pin_brand_colors_preserves_subject_field():
    result = pin_brand_colors(_theme("Nvidia"), BRAND_COLORS)
    assert result["subject"] == "Nvidia"


LAYOUT_RULES = {
    "breaking": ["launch", "launches", "announces", "unveils"],
    "editorial": ["analysis", "opinion", "deep dive", "explainer"],
}


def test_select_layout_matches_breaking():
    item = {"title": "Nvidia launches new GPU", "summary": ""}
    assert select_layout(item, LAYOUT_RULES, "slideshow") == "breaking"


def test_select_layout_matches_editorial_in_summary():
    item = {"title": "What happened this week", "summary": "A deep dive into the news."}
    assert select_layout(item, LAYOUT_RULES, "slideshow") == "editorial"


def test_select_layout_first_match_wins_in_rule_order():
    item = {"title": "Analysis: OpenAI launches a new model"}
    assert select_layout(item, LAYOUT_RULES, "slideshow") == "breaking"


def test_select_layout_no_match_returns_default():
    item = {"title": "Just a regular update", "summary": "Nothing special."}
    assert select_layout(item, LAYOUT_RULES, "slideshow") == "slideshow"


def test_select_layout_empty_rules_returns_default():
    assert select_layout({"title": "anything"}, {}, "slideshow") == "slideshow"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/generate/test_style_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.generate.style_rules'`

- [ ] **Step 3: Implement `style_rules.py`**

```python
"""Deterministic, config-driven style choices applied after Claude
generates a post — no LLM prompting involved, so the same subject/topic
always renders with the same recognizable color and layout."""

from __future__ import annotations


def pin_brand_colors(theme: dict, brand_colors: dict) -> dict:
    subject = (theme.get("subject") or "").lower()
    match_key = None
    for key in brand_colors:
        if key.lower() in subject:
            if match_key is None or len(key) > len(match_key):
                match_key = key
    if match_key is None:
        return theme
    palette = brand_colors[match_key]
    return {**theme, **palette, "subject": theme.get("subject")}


def select_layout(item: dict, layout_rules: dict, default_layout: str) -> str:
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    for layout, keywords in layout_rules.items():
        if any(kw.lower() in haystack for kw in keywords):
            return layout
    return default_layout
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/generate/test_style_rules.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/generate/style_rules.py tests/generate/test_style_rules.py
git commit -m "feat: add deterministic brand-color pinning + layout selection rules"
```

---

### Task 2: Config additions + `runner.py` call site

**Files:**
- Modify: `config/settings.yaml`
- Modify: `claudeshorts/generate/runner.py`
- Test: extend existing `tests/generate/test_runner.py` (or equivalent runner test file — check actual name via `ls tests/generate/`)

**Interfaces:**
- Consumes: `style_rules.pin_brand_colors`, `style_rules.select_layout` from Task 1.
- Produces: `runner.py`'s post-generation step now sets `data["theme"]` (pinned) and computes a local `layout` string passed into post creation.

- [ ] **Step 1: Add the config section**

Append to `config/settings.yaml` (after the existing `model:` section):

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

- [ ] **Step 2: Find the exact call site in `runner.py`**

Run: `grep -n "theme=data\[.theme.\]\|create_post\|def generate_for_item\|def run_generate" claudeshorts/generate/runner.py`

This locates the exact line(s) passing `data["theme"]` into post creation
(reported in the earlier chunk-planning session as being near line 42).

- [ ] **Step 3: Write the failing test**

First inspect the existing runner test file to match its fixture/mocking
style: `ls tests/generate/` then read the file that tests
`generate_for_item`/`run_generate`. Add a test asserting the persisted
post's theme reflects brand pinning and its layout reflects rule
matching, e.g. (adapt fixture names to match the file's existing
conventions — this is illustrative of the assertions needed, not a
drop-in replacement for the file's existing setup):

```python
def test_generate_for_item_pins_brand_colors_and_selects_layout(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "claudeshorts.generate.runner.generate_post",
        lambda item, prior_coverage=None, **kw: {
            "title": "T", "thread_slug": "t", "thread_title": "T",
            "thread_summary": "S",
            "theme": {"subject": "Nvidia", "primary": "#111111",
                      "secondary": "#222222", "accent": "#333333", "mood": "light"},
            "slides": [{"headline": "H", "bullets": []}] * 3,
            "captions": {
                "youtube": {"title": "t", "description": "d", "hashtags": []},
                "tiktok": {"caption": "c", "hashtags": []},
                "instagram": {"caption": "c", "hashtags": []},
            },
        },
    )
    item = {"id": 1, "title": "Nvidia launches new GPU", "summary": ""}
    post_id = generate_for_item(item)
    post = posts.get_post(post_id)
    assert post["theme"]["primary"] == "#76B900"
    assert post["layout"] == "breaking"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/generate/ -k pins_brand_colors_and_selects_layout -v`
Expected: FAIL — `KeyError: 'layout'` or theme unchanged (pre-pinning behavior)

- [ ] **Step 5: Implement the `runner.py` change**

At the located call site, before the existing post-creation call, insert:

```python
from ..config import settings
from . import style_rules
...
    style_cfg = settings().get("styles", {})
    data["theme"] = style_rules.pin_brand_colors(data["theme"], style_cfg.get("brand_colors", {}))
    layout = style_rules.select_layout(
        item, style_cfg.get("layout_rules", {}), style_cfg.get("default_layout", "slideshow"),
    )
```

then pass `layout=layout` into the existing `posts.create_post(...)` call
alongside its current `theme=data["theme"]` argument.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/generate/ -k pins_brand_colors_and_selects_layout -v`
Expected: PASS

- [ ] **Step 7: Run the full generate test suite to check for regressions**

Run: `pytest tests/generate/ -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add config/settings.yaml claudeshorts/generate/runner.py tests/generate/
git commit -m "feat: wire brand-color pinning and layout selection into the generation pipeline"
```

---

### Task 3: `posts.layout` storage column

**Files:**
- Modify: `claudeshorts/store/db.py`
- Modify: `claudeshorts/store/posts.py`
- Test: extend `tests/store/test_posts.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `posts.create_post(..., layout: str = "slideshow", ...)`; `get_post`/list functions return `d["layout"]`.

- [ ] **Step 1: Write the failing test**

Add to `tests/store/test_posts.py` (matching its existing fixture/DB-setup
conventions — read the file first for the exact `create_post`/`get_post`
call shape already in use):

```python
def test_create_post_persists_layout(db):
    post_id = posts.create_post(
        db, item_ids=[1], status="draft", title="T",
        slides=[], theme={"subject": "x"}, captions={}, layout="editorial",
    )
    post = posts.get_post(db, post_id)
    assert post["layout"] == "editorial"


def test_create_post_defaults_layout_to_slideshow(db):
    post_id = posts.create_post(
        db, item_ids=[1], status="draft", title="T",
        slides=[], theme={"subject": "x"}, captions={},
    )
    post = posts.get_post(db, post_id)
    assert post["layout"] == "slideshow"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_posts.py -k layout -v`
Expected: FAIL — `TypeError: create_post() got an unexpected keyword argument 'layout'` (or missing column error)

- [ ] **Step 3: Add the migration in `db.py`**

Find `_apply_migrations()`'s list of `(table, column, coltype)` tuples
(the same list containing `("posts", "theme_json", "TEXT")`) and add:

```python
    ("posts", "layout", "TEXT"),
```

Find the `CREATE TABLE posts (...)` statement and add `layout TEXT DEFAULT
'slideshow',` alongside the other post columns, so fresh databases get the
column without relying solely on the migration path.

- [ ] **Step 4: Update `posts.py`**

In `create_post`, add a `layout: str = "slideshow"` parameter and include
it in the `INSERT` column list/values tuple. In the row-to-dict mapper
(the same function that does `d["theme"] = json.loads(...)`), add:

```python
    d["layout"] = row["layout"] or "slideshow"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/store/test_posts.py -k layout -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the full store test suite to check for regressions**

Run: `pytest tests/store/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add claudeshorts/store/db.py claudeshorts/store/posts.py tests/store/test_posts.py
git commit -m "feat: add posts.layout column, default slideshow"
```

---

### Task 4: `bridge.py` spec assembly + `render.mjs` template allowlist

**Files:**
- Modify: `claudeshorts/render/bridge.py`
- Modify: `renderer/render.mjs`
- Test: extend `tests/render/test_bridge.py`

**Interfaces:**
- Consumes: `post["layout"]` from Task 3.
- Produces: render spec dict gains `"layout"` key; `render.mjs` resolves it to a template file via an explicit allowlist.

- [ ] **Step 1: Write the failing test**

Add to `tests/render/test_bridge.py` (match existing fixture conventions):

```python
def test_build_spec_includes_layout():
    post = {"theme": {}, "layout": "breaking", "slides": [], "captions": {}}
    spec = build_render_spec(post, channel={}, video_settings={}, audio_settings={})
    assert spec["layout"] == "breaking"


def test_build_spec_defaults_layout_to_slideshow_when_missing():
    post = {"theme": {}, "slides": [], "captions": {}}
    spec = build_render_spec(post, channel={}, video_settings={}, audio_settings={})
    assert spec["layout"] == "slideshow"
```

(Adjust the imported function name to whatever `bridge.py` actually calls
its spec-assembly function — confirm with `grep -n "^def " claudeshorts/render/bridge.py`
before writing this step for real.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/render/test_bridge.py -k layout -v`
Expected: FAIL — `KeyError: 'layout'`

- [ ] **Step 3: Implement the `bridge.py` change**

At `render/bridge.py:102` (where `"theme": post.get("theme") or {}` is
built), add the adjacent line:

```python
        "layout": post.get("layout") or "slideshow",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/render/test_bridge.py -k layout -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Implement the `render.mjs` allowlist**

In `renderer/render.mjs`, find the existing constant:

```js
const TEMPLATE = join(HERE, "templates", "slideshow.html");
```

Replace with a function called at spec-load time (after the spec JSON is
parsed, before the page navigates to the template):

```js
const LAYOUTS = { slideshow: "slideshow.html", editorial: "editorial.html", breaking: "breaking.html" };
function templatePathFor(layout) {
  const file = LAYOUTS[layout] || LAYOUTS.slideshow;
  return join(HERE, "templates", file);
}
```

Update the call site that previously referenced the `TEMPLATE` constant to
call `templatePathFor(spec.layout)` instead (find it via `grep -n
"TEMPLATE" renderer/render.mjs`).

- [ ] **Step 6: Run the renderer's existing test/check**

Run: `node --check renderer/render.mjs`
Expected: no syntax errors

- [ ] **Step 7: Commit**

```bash
git add claudeshorts/render/bridge.py renderer/render.mjs tests/render/test_bridge.py
git commit -m "feat: thread layout through render spec assembly with an allowlisted template lookup"
```

---

### Task 5: `editorial.html` template

**Files:**
- Create: `renderer/templates/editorial.html`

**Interfaces:**
- Consumes: the same spec shape `slideshow.html` consumes (`spec.slides`, `spec.theme`, `spec.channel`) via `window.__init(spec)`.
- Produces: `window.__init(spec) -> slideCount`, `window.__render(i, localMs, globalMs)` — same contract as `slideshow.html`, so `render.mjs`'s Playwright-driving loop is untouched.

- [ ] **Step 1: Create the template**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<style>
  :root {
    --primary: #76B900;
    --secondary: #0A0A0A;
    --accent: #FFFFFF;
    --ink: #FFFFFF;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1080px; height: 1920px; overflow: hidden; }
  body {
    font-family: "Georgia", "Iowan Old Style", serif;
    background: var(--secondary);
    color: var(--ink);
    position: relative;
  }
  #bg { position: absolute; inset: 0;
    background: linear-gradient(160deg, var(--secondary) 0%, var(--secondary) 70%, var(--primary) 200%);
    opacity: 0.9; }

  #stage { position: absolute; inset: 0;
    display: flex; flex-direction: column; justify-content: center;
    padding: 160px 110px; gap: 44px; }

  #kicker { font-size: 28px; font-weight: 400; letter-spacing: 6px;
    text-transform: uppercase; color: var(--primary);
    border-top: 2px solid var(--primary); padding-top: 20px; width: fit-content; }

  #headline { font-size: 88px; font-weight: 400; line-height: 1.15;
    letter-spacing: -1px; font-style: italic; }

  #bullets { list-style: none; display: flex; flex-direction: column; gap: 34px;
    margin-top: 12px; }
  #bullets li { font-size: 42px; font-weight: 400; line-height: 1.35;
    display: flex; gap: 22px; align-items: flex-start; opacity: 0; }
  #bullets li::before { content: "—"; flex: 0 0 auto; color: var(--primary);
    font-weight: 700; }

  #handle { position: absolute; bottom: 70px; left: 0; right: 0;
    text-align: center; font-size: 28px; font-weight: 400;
    letter-spacing: 2px; opacity: 0.55; }

  #outro { position: absolute; inset: 0; display: none;
    flex-direction: column; align-items: center; justify-content: center; gap: 48px; }
  #outro img { width: 320px; height: 320px; object-fit: contain; border-radius: 24px; }
  #outro .name { font-size: 56px; font-weight: 400; }
  #outro .cta { font-size: 36px; font-weight: 400; color: var(--primary); font-style: italic; }

  body.light { --ink: #0A0A0A; }
</style>
</head>
<body>
  <div id="bg"></div>
  <div id="stage">
    <div id="kicker" id="kicker-text">ANALYSIS</div>
    <h1 id="headline"><span id="headline-text"></span></h1>
    <ul id="bullets"></ul>
  </div>
  <div id="outro">
    <img id="outro-logo" alt="" />
    <div class="name" id="outro-name"></div>
    <div class="cta" id="outro-cta"></div>
  </div>
  <div id="handle"></div>

<script>
const S = { slides: [], theme: null, channel: null };
const el = (id) => document.getElementById(id);
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const easeOut = (t) => 1 - Math.pow(1 - clamp01(t), 3);

window.__init = function (spec) {
  S.slides = spec.slides || [];
  S.theme = spec.theme || {};
  S.channel = spec.channel || {};
  const t = S.theme;
  const root = document.documentElement.style;
  if (t.primary) root.setProperty("--primary", t.primary);
  if (t.secondary) root.setProperty("--secondary", t.secondary);
  if (t.accent) root.setProperty("--accent", t.accent);
  if (t.mood === "light") document.body.classList.add("light");
  el("handle").textContent = S.channel.handle || "";
  if (S.channel.logo_data_uri) el("outro-logo").src = S.channel.logo_data_uri;
  el("outro-name").textContent = S.channel.name || "";
  el("outro-cta").textContent = "Follow for daily tech & AI";
  return S.slides.length;
};

window.__render = function (i, localMs, globalMs) {
  const slide = S.slides[i] || {};
  const isOutro = i === S.slides.length - 1 && !!S.channel.logo_data_uri;

  el("outro").style.display = isOutro ? "flex" : "none";
  el("stage").style.display = isOutro ? "none" : "flex";
  if (isOutro) {
    const p = easeOut(localMs / 900);
    el("outro").style.opacity = p;
    return;
  }

  document.getElementById("kicker").textContent = (slide.kicker || (i === 0 ? "ANALYSIS" : "CONTEXT"));
  el("headline-text").textContent = slide.headline || "";
  const hp = easeOut(localMs / 900);
  const h = el("headline");
  h.style.opacity = hp;
  h.style.transform = `translateY(${(1 - hp) * 24}px)`;

  const ul = el("bullets");
  const bullets = slide.bullets || [];
  if (ul.dataset.k !== i + ":" + bullets.length) {
    ul.innerHTML = "";
    bullets.forEach((b) => { const li = document.createElement("li");
      li.textContent = b; ul.appendChild(li); });
    ul.dataset.k = i + ":" + bullets.length;
  }
  [...ul.children].forEach((li, k) => {
    const bp = easeOut((localMs - 700 - k * 260) / 700);
    li.style.opacity = bp;
    li.style.transform = `translateY(${(1 - bp) * 20}px)`;
  });
};
</script>
</body>
</html>
```

- [ ] **Step 2: Verify with node's syntax check on the extracted script**

Run: `node --check renderer/templates/editorial.html 2>&1 | head -5 || true`
(Node will reject the outer HTML — this is just a smoke check that the
`<script>` block itself has no obvious syntax error visible via manual
read; the authoritative check is Task 6's live render.)

- [ ] **Step 3: Commit**

```bash
git add renderer/templates/editorial.html
git commit -m "feat: add editorial renderer layout (calm, whitespace-heavy, for deep-dive posts)"
```

---

### Task 6: `breaking.html` template + live render verification

**Files:**
- Create: `renderer/templates/breaking.html`

**Interfaces:**
- Same contract as Task 5.

- [ ] **Step 1: Create the template**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<style>
  :root {
    --primary: #76B900;
    --secondary: #0A0A0A;
    --accent: #FFFFFF;
    --ink: #FFFFFF;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1080px; height: 1920px; overflow: hidden; }
  body {
    font-family: "Inter", "Helvetica Neue", Arial, sans-serif;
    background: var(--secondary);
    color: var(--ink);
    position: relative;
  }
  #bg { position: absolute; inset: 0; overflow: hidden; }
  .blob { position: absolute; border-radius: 50%; filter: blur(70px); opacity: 0.7; }
  .blob.a { width: 1100px; height: 1100px; background: var(--primary); }
  .blob.b { width: 900px; height: 900px; background: var(--accent); opacity: 0.25; }

  #ticker { position: absolute; top: 0; left: 0; right: 0; height: 96px;
    background: var(--primary); display: flex; align-items: center;
    justify-content: center; gap: 20px; }
  #ticker span { font-size: 40px; font-weight: 900; letter-spacing: 6px;
    text-transform: uppercase; color: var(--secondary); }
  #ticker .dot { width: 20px; height: 20px; border-radius: 50%; background: var(--secondary); }

  #stage { position: absolute; inset: 0;
    display: flex; flex-direction: column; justify-content: center;
    padding: 220px 90px 140px; gap: 36px; }

  #headline { font-size: 120px; font-weight: 900; line-height: 0.98;
    letter-spacing: -3px; text-transform: uppercase; }

  #bullets { list-style: none; display: flex; flex-direction: column; gap: 26px;
    margin-top: 16px; }
  #bullets li { font-size: 48px; font-weight: 800; line-height: 1.2;
    display: flex; gap: 20px; align-items: flex-start; opacity: 0; }
  #bullets li::before { content: ""; flex: 0 0 auto; width: 24px; height: 24px;
    margin-top: 14px; background: var(--primary); }

  #handle { position: absolute; bottom: 70px; left: 0; right: 0;
    text-align: center; font-size: 32px; font-weight: 900;
    letter-spacing: 1px; opacity: 0.7; }

  #outro { position: absolute; inset: 0; display: none;
    flex-direction: column; align-items: center; justify-content: center; gap: 48px; }
  #outro img { width: 360px; height: 360px; object-fit: contain; border-radius: 40px; }
  #outro .name { font-size: 64px; font-weight: 900; }
  #outro .cta { font-size: 40px; font-weight: 700; color: var(--primary); }

  body.light { --ink: #0A0A0A; }
</style>
</head>
<body>
  <div id="bg"><div class="blob a"></div><div class="blob b"></div></div>
  <div id="ticker"><div class="dot"></div><span id="ticker-text">BREAKING</span><div class="dot"></div></div>
  <div id="stage">
    <h1 id="headline"><span id="headline-text"></span></h1>
    <ul id="bullets"></ul>
  </div>
  <div id="outro">
    <img id="outro-logo" alt="" />
    <div class="name" id="outro-name"></div>
    <div class="cta" id="outro-cta"></div>
  </div>
  <div id="handle"></div>

<script>
const S = { slides: [], theme: null, channel: null };
const el = (id) => document.getElementById(id);
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const easeOut = (t) => 1 - Math.pow(1 - clamp01(t), 3);

window.__init = function (spec) {
  S.slides = spec.slides || [];
  S.theme = spec.theme || {};
  S.channel = spec.channel || {};
  const t = S.theme;
  const root = document.documentElement.style;
  if (t.primary) root.setProperty("--primary", t.primary);
  if (t.secondary) root.setProperty("--secondary", t.secondary);
  if (t.accent) root.setProperty("--accent", t.accent);
  if (t.mood === "light") document.body.classList.add("light");
  el("handle").textContent = S.channel.handle || "";
  if (S.channel.logo_data_uri) el("outro-logo").src = S.channel.logo_data_uri;
  el("outro-name").textContent = S.channel.name || "";
  el("outro-cta").textContent = "Follow for daily tech & AI";
  return S.slides.length;
};

function paintBg(globalMs) {
  const a = el("bg").querySelector(".blob.a");
  const b = el("bg").querySelector(".blob.b");
  const s = globalMs / 1000;
  a.style.left = (100 + 200 * Math.sin(s * 1.1)) + "px";
  a.style.top = (140 + 240 * Math.cos(s * 0.9)) + "px";
  b.style.right = (80 + 220 * Math.sin(s * 0.8 + 1)) + "px";
  b.style.bottom = (160 + 200 * Math.cos(s * 1.2 + 2)) + "px";
}

window.__render = function (i, localMs, globalMs) {
  paintBg(globalMs);
  const slide = S.slides[i] || {};
  const isOutro = i === S.slides.length - 1 && !!S.channel.logo_data_uri;

  el("outro").style.display = isOutro ? "flex" : "none";
  el("stage").style.display = isOutro ? "none" : "flex";
  document.getElementById("ticker").style.display = isOutro ? "none" : "flex";
  if (isOutro) {
    const p = easeOut(localMs / 400);
    el("outro").style.opacity = p;
    return;
  }

  document.getElementById("ticker-text").textContent = (slide.kicker || "BREAKING");
  const pulse = 0.85 + 0.15 * Math.sin(globalMs / 260);
  document.getElementById("ticker").style.opacity = pulse;

  el("headline-text").textContent = slide.headline || "";
  const hp = easeOut(localMs / 300);
  const h = el("headline");
  h.style.opacity = hp;
  h.style.transform = `translateY(${(1 - hp) * 30}px) scale(${0.96 + 0.04 * hp})`;

  const ul = el("bullets");
  const bullets = slide.bullets || [];
  if (ul.dataset.k !== i + ":" + bullets.length) {
    ul.innerHTML = "";
    bullets.forEach((b) => { const li = document.createElement("li");
      li.textContent = b; ul.appendChild(li); });
    ul.dataset.k = i + ":" + bullets.length;
  }
  [...ul.children].forEach((li, k) => {
    const bp = easeOut((localMs - 250 - k * 150) / 450);
    li.style.opacity = bp;
    li.style.transform = `translateX(${(1 - bp) * -30}px)`;
  });
};
</script>
</body>
</html>
```

- [ ] **Step 2: Commit the template**

```bash
git add renderer/templates/breaking.html
git commit -m "feat: add breaking renderer layout (urgent, ticker banner, fast stagger)"
```

- [ ] **Step 3: Live render verification (manual, documented per spec's testing section)**

Pick one existing draft/rendered post id from `data/app.db` for each of the
three layouts (query `SELECT id FROM posts LIMIT 3` or reuse known ids from
prior checkpoints), temporarily set `layout` on each via direct DB update
or by regenerating a post after Task 2/3 land, then run the existing
render CLI command (`python -m claudeshorts.cli render <post_id>` — confirm
exact command name via `python -m claudeshorts.cli --help`) for each. Open
each resulting `renders/post_<id>/video.mp4` and confirm: `slideshow`
looks unchanged from before this chunk, `editorial` shows calm whitespace
with no blob background, `breaking` shows the pulsing ticker banner and
faster bullet stagger. This step is manual per the spec's accepted
limitation (no visual regression harness) — record the outcome in the
Task 7 checkpoint update rather than skipping it silently.

- [ ] **Step 4: Run the full test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: PASS

---

### Task 7: Update checkpoint and task tracking

**Files:**
- Modify: `CHECKPOINT_LAST.md`, `TASK_QUEUE.md`

- [ ] **Step 1: Record completion**

Update `TASK_QUEUE.md` to move chunk 8 to Done. Update `CHECKPOINT_LAST.md`
with: brand-color/layout mechanism summary, the manual live-render
verification outcome from Task 6 Step 3, and next action: chunk 9
(Contexto research note).

- [ ] **Step 2: Commit**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 8 complete — brand color pinning + editorial/breaking layouts live"
```

---

## Self-Review Notes

**Spec coverage:** Brand color pinning (Task 1-2) matches the spec's
longest-match, case-insensitive, unchanged-on-no-match design. Layout
selection (Task 1-2) matches the spec's first-match-in-insertion-order
rule with a default fallback. `posts.layout` storage (Task 3) matches the
spec's new column + default. `bridge.py`/`render.mjs` (Task 4) matches the
spec's allowlist requirement — layout never becomes a raw filesystem path.
Two new templates (Tasks 5-6) both implement the spec's required
`window.__init`/`window.__render` contract with no new spec fields.
Manual visual verification (Task 6 Step 3) matches the spec's explicitly
accepted no-visual-regression-harness limitation.

**Placeholder scan:** Task 2 Step 3 and Task 4 Step 1 include a note to
confirm exact existing function/file names via `grep` before writing the
real assertion — this is flagged inline as a required confirmation step,
not a skipped detail, because the current session's context does not
have the exact current signatures memorized for `runner.py`'s
post-creation call site or `bridge.py`'s spec-assembly function name.
Task 6 Step 3's manual verification has concrete steps (which command,
which files, what to look for) rather than a vague "verify it looks
right."

**Type consistency:** `pin_brand_colors(theme, brand_colors)` and
`select_layout(item, layout_rules, default_layout)` signatures are
identical between Task 1's implementation and Task 2's call site.
`layout` as a plain `str` flows unchanged from `style_rules.select_layout`
(Task 1) through `runner.py` (Task 2) through `posts.create_post`'s new
parameter (Task 3) through `bridge.py`'s spec dict (Task 4) through
`render.mjs`'s `LAYOUTS` lookup (Task 4) — no type changes at any hop.
