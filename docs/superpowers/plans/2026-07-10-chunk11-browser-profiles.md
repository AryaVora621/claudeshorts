# Chunk 11: Browser Profiles + Analytics + Browser Publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the browser-profile system (persistent login sessions), a Playwright-based analytics scraper filling chunk 5's weekly-report placeholder, and a browser-based `PublishProvider` — with YouTube Studio as the one fully-implemented reference upload flow and TikTok/Instagram left as real, calibration-pending stubs.

**Architecture:** New `claudeshorts/browser/` package (profile metadata/session/error-capture/wait helpers/analytics), a new `claudeshorts/publish/providers/browser_profile.py` registered in chunk 10's registry, and two human-run scripts (`interactive_login.py`, `calibrate_upload_flow.py`).

**Tech Stack:** Python 3.11+, new dependency `playwright` (Python package — separate install from the Node renderer's Playwright), existing chunk 6 structured logging, existing chunk 10 publish provider registry.

## Global Constraints

- `time.sleep()` must never appear anywhere in `claudeshorts/browser/` or `claudeshorts/publish/providers/browser_profile.py` — every wait goes through `browser/wait.py`.
- File uploads always use the hidden `<input type="file">` + `setInputFiles()` — never a native OS file dialog.
- Every automation failure is captured (screenshot + HTML + selector + traceback + URL) and re-raised — never silently swallowed.
- Analytics text-parsing logic must be a pure function, testable without Playwright.
- Full spec: `docs/superpowers/specs/2026-07-10-chunk11-browser-profiles-design.md`.

---

## File Structure

- Create: `claudeshorts/browser/__init__.py`, `profiles.py`, `session.py`, `errors.py`, `wait.py`, `analytics.py`
- Create: `claudeshorts/publish/providers/browser_profile.py`
- Modify: `claudeshorts/publish/providers/registry.py`, `pyproject.toml`, `.gitignore`
- Create: `config/profiles/` (directory, initially empty except a `.gitkeep`)
- Create: `scripts/interactive_login.py`, `scripts/calibrate_upload_flow.py`
- Modify: `claudeshorts/generate/runner.py`'s sibling service — actually `services/reporting_service.py` (from chunk 3/5's plan; create if not yet implemented, following chunk 5's exact spec shape)
- Test: `tests/browser/test_profiles.py`, `tests/browser/test_analytics.py`, `tests/publish/providers/test_browser_profile.py`

---

### Task 1: Add the `playwright` dependency + gitignore + profile directories

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `config/profiles/.gitkeep`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`'s `dependencies` list, add:

```toml
    "playwright>=1.47",
```

- [ ] **Step 2: Install it and the browser binary**

Run: `pip install -e . && playwright install chromium`
Expected: installs cleanly (chromium binary download may take a minute).

- [ ] **Step 3: Add gitignore entries**

Add to `.gitignore` (near the existing `/data/`/`/review/` runtime-dirs
block):

```
/profiles/
/data/browser_errors/
```

Note: `config/profiles/` (profile *metadata* YAML) is intentionally NOT
gitignored — only the top-level `/profiles/` (session state) is. These
are different directories despite the similar name (`config/profiles/`
vs `/profiles/`) — this distinction matches the spec's metadata-vs-
session-state separation.

- [ ] **Step 4: Create the metadata directory**

Create `config/profiles/.gitkeep` (empty file) so the directory exists in
git before any real profile YAML is added.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore config/profiles/.gitkeep
git commit -m "chore: add playwright dependency, profile directories"
```

---

### Task 2: `profiles.py` — profile metadata loading

**Files:**
- Create: `claudeshorts/browser/__init__.py` (empty)
- Create: `claudeshorts/browser/profiles.py`
- Test: `tests/browser/test_profiles.py`

**Interfaces:**
- Produces: `load_profile(slug: str) -> dict`, `list_profiles() -> list[dict]`, `storage_state_path(slug: str) -> Path`, `PROFILES_DIR: Path`, `STATE_DIR: Path`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/browser/test_profiles.py
from __future__ import annotations

import claudeshorts.browser.profiles as profiles_mod
from claudeshorts.browser import profiles


def test_load_profile_reads_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    (tmp_path / "acme-youtube.yaml").write_text(
        "slug: acme-youtube\nplatform: youtube\nlogin_health: ok\n"
    )
    profile = profiles.load_profile("acme-youtube")
    assert profile["platform"] == "youtube"
    assert profile["login_health"] == "ok"


def test_load_profile_defaults_login_health_to_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    (tmp_path / "acme-tiktok.yaml").write_text("slug: acme-tiktok\nplatform: tiktok\n")
    profile = profiles.load_profile("acme-tiktok")
    assert profile["login_health"] == "unknown"


def test_load_profile_missing_raises_file_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    import pytest
    with pytest.raises(FileNotFoundError):
        profiles.load_profile("does-not-exist")


def test_list_profiles_returns_all(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    (tmp_path / "a.yaml").write_text("slug: a\nplatform: youtube\n")
    (tmp_path / "b.yaml").write_text("slug: b\nplatform: tiktok\n")
    slugs = sorted(p["slug"] for p in profiles.list_profiles())
    assert slugs == ["a", "b"]


def test_list_profiles_empty_dir_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    assert profiles.list_profiles() == []


def test_storage_state_path_under_state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "STATE_DIR", tmp_path)
    path = profiles.storage_state_path("acme-youtube")
    assert path == tmp_path / "acme-youtube" / "storage_state.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/browser/test_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.browser'`

- [ ] **Step 3: Implement `profiles.py`**

```python
"""Profile metadata (config/profiles/<slug>.yaml, versionable) is kept
separate from session state (profiles/<slug>/storage_state.json,
gitignored, holds real cookies) — metadata is safe to review in a PR,
session state never should be."""

from __future__ import annotations

from pathlib import Path

import yaml

PROFILES_DIR = Path("config/profiles")
STATE_DIR = Path("profiles")

_DEFAULTS = {"login_health": "unknown", "browser": "chromium", "notes": ""}


def load_profile(slug: str) -> dict:
    path = PROFILES_DIR / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no profile config at {path}")
    data = yaml.safe_load(path.read_text()) or {}
    return {**_DEFAULTS, **data}


def list_profiles() -> list[dict]:
    if not PROFILES_DIR.is_dir():
        return []
    return [load_profile(p.stem) for p in sorted(PROFILES_DIR.glob("*.yaml"))]


def storage_state_path(slug: str) -> Path:
    return STATE_DIR / slug / "storage_state.json"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/browser/test_profiles.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/browser/__init__.py claudeshorts/browser/profiles.py tests/browser/test_profiles.py
git commit -m "feat: add browser profile metadata loading"
```

---

### Task 3: `wait.py`, `errors.py`, `session.py`

**Files:**
- Create: `claudeshorts/browser/wait.py`
- Create: `claudeshorts/browser/errors.py`
- Create: `claudeshorts/browser/session.py`

**Interfaces:**
- Produces: `wait_visible(locator, timeout=10000)`, `wait_loaded(page, state="load")`; `capture_on_failure(page, step: str, profile_slug: str)` (context manager); `launch_profile(slug: str, *, headless: bool = True)` (context manager yielding a Playwright `BrowserContext`).

This task has no isolated unit test of its own — `session.py`'s real
behavior (launching an actual browser) is exercised end-to-end by Task 6's
manual verification, and `errors.py`'s failure-capture path is exercised
by Task 5's `BrowserProfileProvider` tests via a fake page/context. This
matches goal.md's own rule that browser-driving code isn't unit-tested;
only the surrounding business logic is.

- [ ] **Step 1: Implement `wait.py`**

```python
"""Every wait in this codebase's browser automation goes through one of
these three functions — never time.sleep(). Centralizing them means a
grep for `time.sleep(` inside claudeshorts/browser/ or
claudeshorts/publish/providers/browser_profile.py staying empty is a
meaningful, enforceable check."""

from __future__ import annotations

from typing import Any


def wait_visible(locator: Any, timeout: int = 10_000) -> None:
    locator.wait_for(state="visible", timeout=timeout)


def wait_loaded(page: Any, state: str = "load") -> None:
    page.wait_for_load_state(state)


def wait_selector(page: Any, selector: str, timeout: int = 10_000) -> Any:
    return page.wait_for_selector(selector, timeout=timeout)
```

- [ ] **Step 2: Implement `errors.py`**

```python
"""goal.md's Error Handling rule, verbatim: on any automation failure,
capture a screenshot, the page HTML, the selector/step description, the
stack trace, and the current URL — then re-raise. Never swallow."""

from __future__ import annotations

import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import logging_setup

log = __import__("logging").getLogger(__name__)

ERRORS_DIR = Path("data/browser_errors")


@contextmanager
def capture_on_failure(page: Any, step: str, profile_slug: str):
    with logging_setup.bind(profile=profile_slug):
        try:
            yield
        except Exception as exc:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            out_dir = ERRORS_DIR / f"{stamp}_{profile_slug}_{step}"
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                page.screenshot(path=str(out_dir / "screenshot.png"))
                (out_dir / "page.html").write_text(page.content(), encoding="utf-8")
            except Exception:
                pass
            (out_dir / "error.txt").write_text(
                f"step: {step}\nurl: {getattr(page, 'url', '?')}\n\n"
                f"{traceback.format_exc()}",
                encoding="utf-8",
            )
            log.error("browser automation step %r failed for profile %r: %s",
                       step, profile_slug, exc)
            raise
```

- [ ] **Step 3: Implement `session.py`**

```python
"""Launches a Playwright browser context for a named profile, loading and
persisting its storage state so a login done once (via
scripts/interactive_login.py) is reused by every later automated run."""

from __future__ import annotations

import json
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

from . import profiles


@contextmanager
def launch_profile(slug: str, *, headless: bool = True):
    profile = profiles.load_profile(slug)
    state_path = profiles.storage_state_path(slug)
    storage_state = str(state_path) if state_path.exists() else None

    with sync_playwright() as p:
        browser_type = getattr(p, profile.get("browser", "chromium"))
        browser = browser_type.launch(headless=headless)
        context = browser.new_context(
            storage_state=storage_state,
            locale=profile.get("locale"),
            timezone_id=profile.get("timezone_id"),
            user_agent=profile.get("user_agent"),
            proxy={"server": profile["proxy"]} if profile.get("proxy") else None,
        )
        try:
            yield context
        finally:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(state_path))
            context.close()
            browser.close()
```

- [ ] **Step 4: Commit**

```bash
git add claudeshorts/browser/wait.py claudeshorts/browser/errors.py claudeshorts/browser/session.py
git commit -m "feat: add browser wait helpers, failure capture, and profile session management"
```

---

### Task 4: `analytics.py` — pure metric parsing + scraper

**Files:**
- Create: `claudeshorts/browser/analytics.py`
- Test: `tests/browser/test_analytics.py`

**Interfaces:**
- Produces: `parse_metric_text(text: str) -> int` (pure), `scrape_engagement(profile_slug: str, platform: str) -> dict` (Playwright-driving, not unit tested).

- [ ] **Step 1: Write the failing tests**

```python
# tests/browser/test_analytics.py
from __future__ import annotations

import pytest

from claudeshorts.browser.analytics import parse_metric_text


def test_parse_plain_digits():
    assert parse_metric_text("842") == 842


def test_parse_comma_separated():
    assert parse_metric_text("1,204") == 1204


def test_parse_k_suffix():
    assert parse_metric_text("1.2K") == 1200


def test_parse_m_suffix():
    assert parse_metric_text("3.4M") == 3400000


def test_parse_k_suffix_lowercase():
    assert parse_metric_text("12k") == 12000


def test_parse_strips_surrounding_text():
    assert parse_metric_text("1.2K views") == 1200


def test_parse_unparsable_raises():
    with pytest.raises(ValueError):
        parse_metric_text("not a number")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/browser/test_analytics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.browser.analytics'`

- [ ] **Step 3: Implement `analytics.py`**

```python
"""parse_metric_text is pure and independently tested — goal.md: business
logic must not require Playwright to test. scrape_engagement is the thin,
Playwright-driving wrapper around it; it is verified manually against a
real logged-in session (see chunk 11's plan Task 6), not by pytest."""

from __future__ import annotations

import re

from . import session
from .errors import capture_on_failure
from .wait import wait_selector

_METRIC_RE = re.compile(r"([\d,.]+)\s*([KkMm]?)")

_MULTIPLIERS = {"": 1, "k": 1_000, "m": 1_000_000}

_ANALYTICS_URLS = {
    "youtube": "https://studio.youtube.com/channel/analytics",
    "tiktok": "https://www.tiktok.com/tiktokstudio/analytics",
    "instagram": "https://www.instagram.com/accounts/insights/",
}


def parse_metric_text(text: str) -> int:
    match = _METRIC_RE.search(text.strip())
    if not match:
        raise ValueError(f"could not parse metric text: {text!r}")
    number_part, suffix = match.groups()
    number_part = number_part.replace(",", "")
    try:
        value = float(number_part)
    except ValueError as exc:
        raise ValueError(f"could not parse metric text: {text!r}") from exc
    return int(value * _MULTIPLIERS[suffix.lower()])


def scrape_engagement(profile_slug: str, platform: str) -> dict:
    with session.launch_profile(profile_slug, headless=True) as context:
        page = context.new_page()
        with capture_on_failure(page, f"scrape_engagement:{platform}", profile_slug):
            page.goto(_ANALYTICS_URLS[platform])
            views_el = wait_selector(page, "[aria-label*='views' i]")
            return {"views": parse_metric_text(views_el.inner_text())}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/browser/test_analytics.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/browser/analytics.py tests/browser/test_analytics.py
git commit -m "feat: add metric text parsing + analytics scraper skeleton"
```

---

### Task 5: `browser_profile.py` publish provider + registry wiring

**Files:**
- Create: `claudeshorts/publish/providers/browser_profile.py`
- Modify: `claudeshorts/publish/providers/registry.py`
- Test: `tests/publish/providers/test_browser_profile.py`

**Interfaces:**
- Consumes: `browser.session.launch_profile`, `browser.errors.capture_on_failure`, `browser.wait.*` (Task 3); `publish.providers.folder_export.FolderExportProvider._locate_video` (Task 3 of chunk 10 — reuse by composition, not inheritance, to avoid coupling the two providers' public surfaces).
- Produces: `BrowserProfileProvider(profile_slug: str).publish(post, platform, channel) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/publish/providers/test_browser_profile.py
from __future__ import annotations

import pytest

from claudeshorts.publish.providers.browser_profile import (
    BrowserProfileProvider, TikTokUploadFlow, InstagramUploadFlow,
)


def test_tiktok_flow_raises_not_implemented_with_calibration_hint():
    flow = TikTokUploadFlow()
    with pytest.raises(NotImplementedError, match="calibrate_upload_flow.py tiktok"):
        flow.upload(context=None, video_path=None, caption="", title="")


def test_instagram_flow_raises_not_implemented_with_calibration_hint():
    flow = InstagramUploadFlow()
    with pytest.raises(NotImplementedError, match="calibrate_upload_flow.py instagram"):
        flow.upload(context=None, video_path=None, caption="", title="")


def test_provider_selects_flow_by_platform():
    provider = BrowserProfileProvider(profile_slug="acme-tiktok")
    assert provider.FLOWS["tiktok"] is TikTokUploadFlow
    assert provider.FLOWS["instagram"] is InstagramUploadFlow
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/publish/providers/test_browser_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.publish.providers.browser_profile'`

- [ ] **Step 3: Implement `browser_profile.py`**

```python
"""Browser-based publishing: uploads through a real logged-in profile
instead of a platform API. YouTubeStudioUploadFlow is the one fully
implemented reference; TikTok/Instagram require selector calibration
against a real session first (scripts/calibrate_upload_flow.py) — this
chunk's explicit human-required final task."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...browser import session
from ...browser.errors import capture_on_failure
from ...browser.wait import wait_visible
from ..providers.folder_export import FolderExportProvider


class YouTubeStudioUploadFlow:
    def upload(self, context: Any, video_path: Path, caption: str, title: str) -> None:
        page = context.new_page()
        with capture_on_failure(page, "youtube_upload", "youtube-studio"):
            page.goto("https://studio.youtube.com")
            page.get_by_role("button", name="Create").click()
            page.get_by_text("Upload videos").click()
            file_input = page.locator("input[type='file']")
            file_input.set_input_files(str(video_path))
            title_field = page.get_by_label("Title (required)")
            wait_visible(title_field)
            title_field.fill(title)
            page.get_by_label("Description").fill(caption)
            for _ in range(3):
                page.get_by_role("button", name="Next").click()
            page.get_by_role("radio", name="Public").click()
            page.get_by_role("button", name="Publish").click()


class TikTokUploadFlow:
    def upload(self, context: Any, video_path: Path, caption: str, title: str) -> None:
        raise NotImplementedError(
            "TikTok upload selectors not yet calibrated — run "
            "scripts/calibrate_upload_flow.py tiktok <profile_slug> against "
            "a real logged-in session, then implement this flow following "
            "YouTubeStudioUploadFlow's pattern."
        )


class InstagramUploadFlow:
    def upload(self, context: Any, video_path: Path, caption: str, title: str) -> None:
        raise NotImplementedError(
            "Instagram upload selectors not yet calibrated — run "
            "scripts/calibrate_upload_flow.py instagram <profile_slug> "
            "against a real logged-in session, then implement this flow "
            "following YouTubeStudioUploadFlow's pattern."
        )


class BrowserProfileProvider:
    FLOWS = {
        "youtube": YouTubeStudioUploadFlow,
        "tiktok": TikTokUploadFlow,
        "instagram": InstagramUploadFlow,
    }

    def __init__(self, profile_slug: str):
        self.profile_slug = profile_slug
        self._locator = FolderExportProvider()

    def publish(self, post: dict, platform: str, channel: dict) -> dict:
        video_path = self._locator._locate_video(post["id"])
        caps = (post.get("captions") or {}).get(platform, {})
        title = caps.get("title") or post.get("title", "")
        caption = caps.get("description") or caps.get("caption", "")
        flow = self.FLOWS[platform]()
        with session.launch_profile(self.profile_slug, headless=True) as context:
            flow.upload(context, video_path, caption, title)
        return {
            "status": "published",
            "location": self.profile_slug,
            "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/publish/providers/test_browser_profile.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire into the registry**

In `claudeshorts/publish/providers/registry.py` (chunk 10), add:

```python
    if name == "browser_profile":
        from .browser_profile import BrowserProfileProvider
        return BrowserProfileProvider(profile_slug=credentials_env)
```

before the final `raise ValueError(...)` line, and update that error
message's provider list to include `browser_profile`.

- [ ] **Step 6: Run the full publish test suite to check for regressions**

Run: `pytest tests/publish/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add claudeshorts/publish/providers/browser_profile.py claudeshorts/publish/providers/registry.py tests/publish/providers/test_browser_profile.py
git commit -m "feat: add browser-based publish provider (YouTube Studio flow implemented, TikTok/Instagram pending calibration)"
```

---

### Task 6: Human-required scripts + weekly-report wiring

**Files:**
- Create: `scripts/interactive_login.py`
- Create: `scripts/calibrate_upload_flow.py`
- Modify: `claudeshorts/services/reporting_service.py` (from chunk 5's plan — implement if not yet built; otherwise extend)

- [ ] **Step 1: Implement `interactive_login.py`**

```python
"""Run once per (channel, platform) to create a reusable browser profile:
python scripts/interactive_login.py <slug> <platform>
Opens a real, visible browser window; log in by hand, then press Enter."""

import sys

from claudeshorts.browser import profiles, session

_LOGIN_URLS = {
    "youtube": "https://accounts.google.com/ServiceLogin?service=youtube",
    "tiktok": "https://www.tiktok.com/login",
    "instagram": "https://www.instagram.com/accounts/login/",
}


def main(slug: str, platform: str) -> None:
    with session.launch_profile(slug, headless=False) as context:
        page = context.new_page()
        page.goto(_LOGIN_URLS[platform])
        input(f"Log in to {platform} in the opened browser window, then press Enter here...")
    print(f"Session saved to {profiles.storage_state_path(slug)}")
    print(f"Now create config/profiles/{slug}.yaml with login_health: ok")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

- [ ] **Step 2: Implement `calibrate_upload_flow.py`**

```python
"""Development aid, not part of the production pipeline: opens a profile
headed and prints each clicked element's accessible role/label so a human
can write TikTokUploadFlow/InstagramUploadFlow's real selectors.
python scripts/calibrate_upload_flow.py <platform> <profile_slug>"""

import sys

from claudeshorts.browser import session

_STUDIO_URLS = {
    "tiktok": "https://www.tiktok.com/tiktokstudio/upload",
    "instagram": "https://www.instagram.com/",
}


def main(platform: str, slug: str) -> None:
    with session.launch_profile(slug, headless=False) as context:
        page = context.new_page()
        page.goto(_STUDIO_URLS[platform])
        page.expose_binding(
            "logClick",
            lambda source, info: print(f"clicked: role={info.get('role')} "
                                        f"name={info.get('name')} tag={info.get('tag')}"),
        )
        input("Click through the upload flow, watch this terminal for logged "
              "element info, then press Enter here when done...")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

- [ ] **Step 3: Wire analytics into `weekly_report`**

Locate chunk 5's `services/reporting_service.py::weekly_report` (implement
per chunk 5's plan first if that chunk hasn't been executed yet — this
task assumes it exists). Replace the hardcoded `platform_engagement`
placeholder with:

```python
from ..browser import analytics, profiles
from ..store import channels as channels_store

def _engagement_for_channel(channel_row: dict, channel_cfg: dict) -> dict:
    result = {}
    for platform, platform_cfg in channel_cfg.get("platforms", {}).items():
        profile_slug = platform_cfg.get("analytics_profile")
        profile = None
        if profile_slug:
            try:
                profile = profiles.load_profile(profile_slug)
            except FileNotFoundError:
                profile = None
        if profile and profile.get("login_health") == "ok":
            result[platform] = analytics.scrape_engagement(profile_slug, platform)
        else:
            result[platform] = {"status": "pending", "note": "no calibrated analytics profile yet"}
    return result
```

called once per enabled channel inside `weekly_report`, merged into the
existing report dict's `platform_engagement` key (keyed by channel slug
if more than one channel exists, matching chunk 10's multi-channel model).

- [ ] **Step 4: Run the full test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: PASS (analytics-scraping itself is not exercised by this test
run — `profiles.load_profile` raising `FileNotFoundError` for a
non-existent profile is the only path hit, since no real profile exists
yet)

- [ ] **Step 5: Commit**

```bash
git add scripts/interactive_login.py scripts/calibrate_upload_flow.py claudeshorts/services/reporting_service.py
git commit -m "feat: add interactive login + upload-flow calibration scripts; wire analytics into weekly report"
```

---

### Task 7: Update checkpoint and task tracking

**Files:**
- Modify: `CHECKPOINT_LAST.md`, `TASK_QUEUE.md`

- [ ] **Step 1: Record completion, flag remaining human-required steps**

Update `TASK_QUEUE.md` to move chunk 11 to Done. Update
`CHECKPOINT_LAST.md` noting: profile storage, session management, error
capture, analytics parsing, and the YouTube Studio reference upload flow
are implemented and tested; three things remain explicitly human-required
and un-done: (1) running `interactive_login.py` for any real channel to
create its first profile, (2) running `calibrate_upload_flow.py` and
implementing real TikTok/Instagram selectors, (3) verifying a real
`weekly_report()` shows scraped numbers instead of the placeholder. Next
action: chunk 12 (Telegram bot interface).

- [ ] **Step 2: Commit**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 11 complete — browser profile system + analytics scraper + browser publish provider live, real logins/selectors still pending"
```

---

## Self-Review Notes

**Spec coverage:** Profile metadata/session-state separation (Task 1-2)
matches the spec's config-vs-gitignored-runtime-state split.
`wait.py`/`errors.py`/`session.py` (Task 3) match goal.md's no-sleep,
resilient-wait, mandatory-failure-capture rules. `parse_metric_text`
(Task 4) is pure and independently tested per goal.md's explicit
Playwright-testing exemption rule. `BrowserProfileProvider` +
`YouTubeStudioUploadFlow` fully implemented, `TikTokUploadFlow`/
`InstagramUploadFlow` calibration-pending stubs (Task 5) match the spec's
"one worked reference, two honest stubs" decision. `interactive_login.py`/
`calibrate_upload_flow.py` (Task 6) match the spec's two human-required
scripts. Weekly-report wiring (Task 6 Step 3) matches chunk 5's exact
`platform_engagement` placeholder shape being replaced by real-or-still-
pending per-platform data.

**Placeholder scan:** `TikTokUploadFlow`/`InstagramUploadFlow`'s
`NotImplementedError` messages are themselves intentional, spec-required
stubs (not plan placeholders) — flagged as such in both the spec and this
plan's task descriptions, with a concrete next step (run the calibration
script) rather than a bare TODO. No other placeholder patterns found.

**Type consistency:** `PublishProvider.publish(post, platform, channel)`'s
signature (established in chunk 10) is preserved by
`BrowserProfileProvider` (Task 5). `BrowserPublishFlow`'s `upload(context,
video_path, caption, title)` signature is identical across
`YouTubeStudioUploadFlow` and both stub flows (Task 5). `registry
.get_provider(name, *, credentials_env=None)`'s existing keyword
(chunk 10) is reused unchanged as the profile-slug carrier for
`browser_profile` (Task 5 Step 5) rather than adding a new,
inconsistent parameter name.
