# Chunk 11: Browser-automation profile system + Playwright analytics + browser-based publish

## Context

Eleventh of 14 chunks rebuilding claudeshorts per `goal.md`. This is a
deferred, human-required chunk: goal.md's Browser Automation / Browser
Profiles sections (lines 186-274) require Playwright-driven automation
with persistent, reusable login profiles, resilient (aria/role/label/
data-attr, never brittle CSS) selectors, no `time.sleep()`, and mandatory
graceful-failure capture (screenshot + HTML + selector + stack trace +
URL). Chunk 5's weekly report has an explicit "pending — see chunk 11"
placeholder for `platform_engagement`, and this chunk fills it in. Per the
user's confirmed scope for this chunk, it also adds a browser-based
`PublishProvider` (chunk 10's plugin interface) as an alternative to
API-key-based publishing.

**Why this is still "deferred, human-required" despite building real
code:** discovering the actual DOM selectors for YouTube Studio's
upload flow, TikTok's Content posting flow, and Instagram's upload flow
requires a human watching a real, logged-in browser session — this
cannot be done blind from a spec. The scaffolding (profile storage,
session management, error capture, resilient-wait helpers, one worked
reference flow) is built now; per-platform selector calibration is the
explicit final, human-required task, same pattern as chunk 10's API
credential wiring.

## Current state

No Python-side Playwright exists anywhere in this codebase — only the
Node renderer (`renderer/render.mjs`) uses Playwright, purely to capture
frames of static HTML, never to interact with a live logged-in website.
There is no profile concept, no stored browser session state, and chunk
5's `weekly_report()`'s `platform_engagement` field is a hardcoded
`{"status": "pending", ...}` placeholder.

## Decision (confirmed with user)

Three additive pieces, all under a new `claudeshorts/browser/` package,
plus one new `PublishProvider`:

1. **Profile storage** — matching goal.md's explicit `config/profiles/`
   directory convention: each profile's *metadata* (name, browser type,
   locale, timezone, proxy, user agent, notes, login health) lives in
   `config/profiles/<slug>.yaml`; each profile's *session state*
   (cookies/localStorage — the actual login) lives in a gitignored
   `profiles/<slug>/storage_state.json`, written by Playwright's own
   `context.storage_state(path=...)` after a human logs in interactively.
   Metadata and session state are deliberately separate: metadata is
   config (versionable, human-editable), session state is a secret-like
   artifact (never committed, refreshed by Playwright itself).
2. **Session management** (`claudeshorts/browser/session.py`) — a thin
   wrapper that launches a Playwright browser context for a named
   profile, loading `storage_state.json` if present, applying the
   profile's locale/timezone/user-agent/proxy settings, and re-saving
   `storage_state.json` after the session closes (so a session refreshed
   by normal use stays logged in).
3. **Error capture** (`claudeshorts/browser/errors.py`) — a context
   manager wrapping every automation step per goal.md's Error Handling
   section: on any exception, capture a screenshot, the page HTML, the
   selector/step description, the stack trace, and the current URL (all
   written under `data/browser_errors/<timestamp>/`), log via chunk 6's
   structured logging (`bind(profile=slug)`), then **re-raise** — never
   silently swallow, per goal.md's explicit rule.
4. **Analytics scraper** (`claudeshorts/browser/analytics.py`) —
   `scrape_engagement(profile_slug, platform) -> dict` navigates to the
   platform's studio/analytics page using a stored profile session and
   extracts view/like/comment counts via resilient selectors. Text
   parsing (`"1.2K views"` -> `1200`) is a **pure function**
   (`parse_metric_text`), independently unit-testable with zero Playwright
   involvement — satisfying goal.md's explicit "business logic should not
   require Playwright to test" rule (line 515). `services/
   reporting_service.py::weekly_report` calls this per channel/platform
   when a profile with `login_health: ok` exists, replacing the "pending"
   placeholder; falls back to the existing placeholder when no usable
   profile exists yet.
5. **Browser-based publish provider**
   (`claudeshorts/publish/providers/browser_profile.py`) —
   `BrowserProfileProvider(profile_slug: str)`, a 4th registry entry
   alongside chunk 10's `folder_export`/`youtube_api`/
   `tiktok_api`/`instagram_api`. Shares `session.py`'s profile launch and
   `errors.py`'s failure capture. File upload always goes through the
   hidden `<input type="file">` + `setInputFiles()`, per goal.md's
   explicit mandatory rule — **never** a native OS file dialog. One
   platform (YouTube Studio) gets a fully worked, selector-complete
   upload flow as the reference implementation; TikTok/Instagram flows
   are real classes with the same shared scaffolding but raise a clear
   `NotImplementedError` pointing at the calibration script below —
   completing them is this chunk's final human-required task.

## Architecture

### `claudeshorts/browser/` (new package)

- `profiles.py` — `load_profile(slug) -> dict` (reads
  `config/profiles/<slug>.yaml`), `list_profiles() -> list[dict]`,
  `storage_state_path(slug) -> Path` (`profiles/<slug>/storage_state.json`,
  under the existing gitignored runtime-dirs convention alongside
  `data/`/`review/`/`publish/`/`renders/`).
- `session.py` — `launch_profile(slug, *, headless=True) ->
  AbstractContextManager[BrowserContext]`: starts Playwright, opens a
  persistent context using the profile's stored storage state (or none,
  for a first-time interactive login), applies
  `locale`/`timezone_id`/`user_agent`/`proxy` from the profile's YAML,
  yields the context, and on exit calls
  `context.storage_state(path=storage_state_path(slug))` to persist any
  session refresh.
- `errors.py` — `capture_on_failure(page, step: str, profile_slug: str)`
  context manager: on exception, writes
  `data/browser_errors/<timestamp>_<profile_slug>_<step>/{screenshot.png,
  page.html, error.txt}` (error.txt holds the step description, current
  URL, and full traceback), logs via `logging_setup.bind(profile=
  profile_slug)` at ERROR level, then re-raises.
- `wait.py` — thin, named wrappers around Playwright's own wait
  primitives (`wait_for_selector`, `wait_for_load_state`,
  `expect(locator).to_be_visible()`) — not because Playwright's own API
  needs hiding, but so every call site in this codebase visibly goes
  through one reviewed module, making a future grep for `time.sleep(`
  (which must never appear) a meaningful lint check.
- `analytics.py` — `parse_metric_text(text: str) -> int` (pure,
  independently tested: `"1.2K"` -> `1200`, `"3.4M"` -> `3400000`, plain
  digits pass through, unparsable text raises `ValueError`) and
  `scrape_engagement(profile_slug: str, platform: str) -> dict` (thin,
  Playwright-driving, manually verified against a real logged-in session
  — not unit tested, matching goal.md's testing philosophy).

### `config/profiles/<slug>.yaml` (new directory)

```yaml
slug: midnight-curiosity-youtube
platform: youtube
browser: chromium
locale: en-US
timezone_id: America/New_York
user_agent: null      # null = Playwright's default for the chosen browser
proxy: null
login_health: unknown  # unknown | ok | expired — updated after each real session
notes: ""
```

One file per (channel, platform) pair a human has set up — e.g.
`midnight-curiosity-youtube.yaml`, `midnight-curiosity-tiktok.yaml`. No
files exist until a human runs the interactive login script (final task);
`list_profiles()` returning `[]` is the normal, expected state until then.

### `claudeshorts/publish/providers/browser_profile.py`

```python
class BrowserPublishFlow(Protocol):
    def upload(self, context, video_path: Path, caption: str, title: str) -> None: ...

class YouTubeStudioUploadFlow:
    """Fully implemented reference flow — YouTube Studio's upload dialog:
    Create button (role=button, name='Create') -> Upload videos ->
    hidden <input type=file> via setInputFiles(video_path) -> title field
    (label 'Title (required)') -> description field (label 'Description')
    -> Next x3 (role=button, name='Next') -> Visibility: Public (role=radio)
    -> Publish (role=button, name='Publish'). Every step wrapped in
    errors.capture_on_failure; every wait uses wait.py, never time.sleep().
    """
    def upload(self, context, video_path, caption, title): ...

class TikTokUploadFlow:
    def upload(self, context, video_path, caption, title):
        raise NotImplementedError(
            "TikTok upload selectors not yet calibrated — run "
            "scripts/calibrate_upload_flow.py tiktok <profile_slug> "
            "against a real logged-in session, then implement this flow "
            "following YouTubeStudioUploadFlow's pattern."
        )

class InstagramUploadFlow:
    def upload(self, context, video_path, caption, title):
        raise NotImplementedError(
            "Instagram upload selectors not yet calibrated — run "
            "scripts/calibrate_upload_flow.py instagram <profile_slug> "
            "against a real logged-in session, then implement this flow "
            "following YouTubeStudioUploadFlow's pattern."
        )

class BrowserProfileProvider:
    """Registered as `browser_profile` in publish.providers.registry
    (chunk 10), alongside folder_export/youtube_api/tiktok_api/
    instagram_api — a channel's platform config picks whichever provider
    fits: folder_export (always works), *_api (once API credentials
    exist), or browser_profile (once a login profile + calibrated flow
    exist)."""
    FLOWS = {"youtube": YouTubeStudioUploadFlow, "tiktok": TikTokUploadFlow,
             "instagram": InstagramUploadFlow}

    def __init__(self, profile_slug: str):
        self.profile_slug = profile_slug

    def publish(self, post: dict, platform: str, channel: dict) -> dict: ...
```

`publish()` locates the rendered video (same `_locate_video` logic as
chunk 10's `FolderExportProvider`), launches the profile via
`session.launch_profile`, picks the platform's `FLOWS` entry, calls
`.upload(context, video_path, caption, title)` inside
`errors.capture_on_failure`, and returns `{"status": "published",
"location": "<platform url if the flow captures one, else the profile
slug>", "published_at": ...}`.

`claudeshorts/publish/providers/registry.py` (chunk 10) gains one more
branch: `if name == "browser_profile": return
BrowserProfileProvider(profile_slug=credentials_env)` — reusing the
existing `credentials_env`-style constructor argument as the profile slug
reference, since both are "the name of the thing this provider needs
that lives outside version control."

### `scripts/interactive_login.py` (new, human-required)

```python
"""Run once per (channel, platform) to create a browser profile: opens a
real, visible browser window, waits for the human to log in manually, then
persists the session so future automation reuses it without prompting for
credentials again."""

def main(slug: str, platform: str) -> None:
    with session.launch_profile(slug, headless=False) as context:
        page = context.new_page()
        page.goto(PLATFORM_LOGIN_URLS[platform])
        input(f"Log in to {platform} in the opened browser window, then press Enter here...")
    print(f"Session saved to {profiles.storage_state_path(slug)}")
```

### `scripts/calibrate_upload_flow.py` (new, human-required)

A companion script that opens a profile's session headed (visible) and
prints each element's accessible role/label/aria attributes as the human
clicks through a real upload flow, to speed up writing
`TikTokUploadFlow`/`InstagramUploadFlow`'s real selectors later — this
script itself is a development aid, not part of the production pipeline.

### `services/reporting_service.py::weekly_report` update

```python
for channel in channels_store.list_enabled_channels(conn):
    for platform, platform_cfg in channel_config(channel)["platforms"].items():
        profile_slug = platform_cfg.get("analytics_profile")
        if profile_slug and profiles.load_profile(profile_slug).get("login_health") == "ok":
            engagement[platform] = analytics.scrape_engagement(profile_slug, platform)
        else:
            engagement[platform] = {"status": "pending", "note": "no calibrated analytics profile yet"}
```

## Out of scope for this chunk

- Actually running the interactive login / calibration scripts against
  real accounts — genuinely requires the user's real logins, this
  chunk's explicit final human-required task.
- TikTok/Instagram upload flow selector implementations — same reason;
  YouTube Studio is the one fully worked reference so the *pattern* is
  proven even though only one flow is real.
- Rotating/multiple profiles per platform (e.g. proxy pools, multi-account
  management beyond one profile per channel+platform) — YAGNI until a
  concrete need for more than one profile per platform surfaces.
- CAPTCHA/2FA handling automation — login is always the human-driven
  `interactive_login.py` script; this chunk never attempts to automate
  around auth challenges.

## Testing

`tests/browser/test_analytics.py` — `parse_metric_text`: `"1.2K"` ->
`1200`, `"3.4M"` -> `3400000`, `"842"` -> `842`, `"1,204"` -> `1204`
(comma-separated), unparsable input raises `ValueError`. No Playwright
involved, per goal.md's testing rule.
`tests/browser/test_profiles.py` — `load_profile`/`list_profiles` read
real YAML fixtures from a temp `config/profiles/` dir; `login_health`
defaults sanely when a profile file omits it.
`tests/publish/providers/test_browser_profile.py` — `BrowserProfileProvider
.publish()` for `tiktok`/`instagram` raises the expected
`NotImplementedError` with the calibration-script message (no real
browser launched — inject a fake `session.launch_profile` for this test);
`youtube`'s `YouTubeStudioUploadFlow` is verified only manually (per
goal.md's Playwright-testing rule), documented as an accepted limitation
matching chunk 8's manual-render-verification precedent.
Manual (documented, not automated, explicitly the final task): run
`interactive_login.py` for one real channel+platform, verify
`login_health` flips to `ok`, then run one real `weekly_report()` and
confirm `platform_engagement` shows real scraped numbers instead of the
placeholder.
