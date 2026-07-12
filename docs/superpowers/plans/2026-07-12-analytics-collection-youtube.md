# Sub-project B Phase 1 (YouTube Analytics Collection) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrape real YouTube Studio analytics (retention/view/subscriber metrics) daily per profile via a logged-in Playwright browser session, store them as a time series, and alert the operator (Telegram + a queryable DB signal) when a profile's login session expires.

**Architecture:** A new `analytics_snapshots` table stores one row per scrape attempt (success or failure) as JSONB metrics, following the existing additive-schema convention. A new `browser/session.py` wraps `rebrowser-playwright` to open a profile-scoped browser context from the storage-state file `browser/profiles.py` already tracks per slug. A new `services/analytics_service.py` orchestrates: open session -> navigate YouTube Studio -> classify outcome (ok / session_expired / transient error) -> parse metrics -> write a snapshot row -> escalate via Telegram on session-expiry or on the 3rd consecutive transient failure. Wired into the existing job/schedule system exactly like `full_run`/`weekly_report`: a new `scrape_analytics` job type in `jobs/registry.py`, seeded as a daily `scrape_analytics:<slug>` schedule per active profile in `scheduling/scheduler.py`.

**Tech Stack:** Python 3, psycopg3 (Postgres/Supabase), `rebrowser-playwright` (new dependency), pytest, existing `services/`/`jobs/`/`scheduling/`/`store/`/`browser/` packages.

## Global Constraints

- Schema changes are additive only: `CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` in `claudeshorts/store/db.py`'s `SCHEMA` string — no migration framework, no destructive changes (per `db.py`'s own docstring convention).
- Phase 1 scope is **YouTube only** — do not add Instagram/TikTok scraping code, table columns, or config in this plan (per the spec's explicit phasing).
- Retention/conversion metrics (average view duration, 7-second retention) are the primary fields; views/subscribers are secondary (per the spec's vanity-metric-noise rationale).
- Session-expiry always alerts via **both** Telegram (`telegram_bot/notify.py::send_notification`) and a DB-queryable status (the snapshot row's `metrics->>'status'`); transient scrape errors do not alert until the 3rd consecutive failure for that profile+platform.
- Dashboard rendering of any of this (banners, charts) is explicitly out of scope for this plan — that is sub-project C's job, once it resumes. This plan only needs to produce data and alerts that a future dashboard task can query.
- Do not write CI tests that require a real browser or a real YouTube login — mock the Playwright page/session boundary in all automated tests; live verification against a real session is a manual step in the final task.
- Follow existing conventions exactly: `conn: psycopg.Connection` first positional arg in store functions, `Jsonb(...)` wrapper for JSON columns, `with connect() as conn:` per call at the service layer, module-level plain functions (not classes) in `services/`.

---

### Task 1: Schema — `analytics_snapshots` table

**Files:**
- Modify: `claudeshorts/store/db.py` (append to the `SCHEMA` string, after the `schedules` table block and its indexes, before the closing `"""`)
- Modify: `tests/store/conftest.py`, `tests/scheduling/conftest.py`, `tests/dashboard/conftest.py`, `tests/scripts/conftest.py`, `tests/api/conftest.py`, `tests/jobs/conftest.py`, `tests/services/conftest.py`, `tests/generate/conftest.py` (add `"analytics_snapshots"` to each file's `_TABLES` tuple)
- Test: `tests/store/test_db.py` (new file, or append if it doesn't exist — check first with `ls tests/store/test_db.py`)

**Interfaces:**
- Produces: a `analytics_snapshots` table with columns `id BIGSERIAL PRIMARY KEY`, `profile_id BIGINT REFERENCES profiles(id)`, `platform TEXT NOT NULL`, `captured_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `metrics JSONB NOT NULL`. Later tasks (`store/analytics.py`) query/insert against this table by name.

- [ ] **Step 1: Add the table definition to `SCHEMA`**

In `claudeshorts/store/db.py`, find the end of the `schedules` table's index block (the line `CREATE UNIQUE INDEX IF NOT EXISTS idx_threads_profile_slug ON threads(profile_id, slug);` right before the closing `"""` of `SCHEMA`). Insert this immediately before that closing `"""`:

```python

-- analytics_snapshots: one row per analytics scrape attempt (success or
-- failure) for a profile+platform, sub-project B. `metrics` always
-- contains a "status" key ("ok" | "session_expired" | "error") plus,
-- when status is "ok", the scraped metric fields themselves — see
-- services/analytics_service.py for the exact metric field names.
CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    profile_id  BIGINT      REFERENCES profiles(id),
    platform    TEXT        NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metrics     JSONB       NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_profile_platform
    ON analytics_snapshots(profile_id, platform, captured_at DESC);
```

- [ ] **Step 2: Add the table to every test suite's truncate list**

Run this to find the exact line in each file:

```bash
grep -n '"schedules",' tests/store/conftest.py tests/scheduling/conftest.py tests/dashboard/conftest.py tests/scripts/conftest.py tests/api/conftest.py tests/jobs/conftest.py tests/services/conftest.py tests/generate/conftest.py
```

In each of the 8 files, the `_TABLES` tuple has a line `"schedules",` — add `"analytics_snapshots",` on its own line immediately after it, e.g.:

```python
_TABLES = (
    "post_threads",
    "pins",
    "jobs",
    "runs",
    "posts",
    "threads",
    "items",
    "schedules",
    "analytics_snapshots",
    "profiles",
)
```

(Exact existing ordering/whitespace varies slightly per file — just add the new line after `"schedules",` and before `"profiles",` in each, preserving that file's existing style.)

- [ ] **Step 3: Write a test confirming the table exists and accepts a row**

Check whether `tests/store/test_db.py` already exists:

```bash
ls tests/store/test_db.py
```

If it doesn't exist, create it with this content. If it exists, append this test function to it:

```python
from __future__ import annotations

from claudeshorts.store import db


def test_analytics_snapshots_table_accepts_a_row(db_conn):
    db_conn.execute(
        "INSERT INTO profiles (slug, display_name) VALUES ('test-profile-1', 'Test Profile 1') "
        "ON CONFLICT (slug) DO NOTHING"
    )
    row = db_conn.execute(
        "INSERT INTO analytics_snapshots (profile_id, platform, metrics) "
        "SELECT id, 'youtube', %s FROM profiles WHERE slug = 'test-profile-1' "
        "RETURNING id, platform, metrics",
        ('{"status": "ok", "views": 100}',),
    ).fetchone()
    assert row["platform"] == "youtube"
    assert row["metrics"]["status"] == "ok"
```

This uses the `db_conn` fixture — confirm it's available in `tests/store/conftest.py` by checking it matches the pattern in `tests/scheduling/conftest.py` (a `db_conn` fixture yielding `db.connect()`). If `tests/store/conftest.py` doesn't already have a `db_conn` fixture, add this to it (same pattern as `tests/scheduling/conftest.py`):

```python
@pytest.fixture
def db_conn():
    with db.connect() as conn:
        yield conn
```

- [ ] **Step 4: Run the test to verify it fails (table doesn't exist yet if Step 1 wasn't applied, or passes if it was)**

Run: `pytest tests/store/test_db.py::test_analytics_snapshots_table_accepts_a_row -v`
Expected: PASS (Step 1 already added the table to `SCHEMA`, and `_clean_tables`'s `db.init_db()` call runs `SCHEMA` idempotently before each test)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/store/db.py tests/store/conftest.py tests/scheduling/conftest.py tests/dashboard/conftest.py tests/scripts/conftest.py tests/api/conftest.py tests/jobs/conftest.py tests/services/conftest.py tests/generate/conftest.py tests/store/test_db.py
git commit -m "feat: add analytics_snapshots table for sub-project B"
```

---

### Task 2: `store/analytics.py` — CRUD for analytics_snapshots

**Files:**
- Create: `claudeshorts/store/analytics.py`
- Modify: `claudeshorts/store/__init__.py` (export the new functions)
- Test: `tests/store/test_analytics.py`

**Interfaces:**
- Consumes: `analytics_snapshots` table from Task 1.
- Produces:
  - `insert_snapshot(conn: psycopg.Connection, *, profile_id: int, platform: str, metrics: dict) -> int` — returns the new row's `id`.
  - `latest_snapshot(conn: psycopg.Connection, *, profile_id: int, platform: str) -> dict | None`
  - `recent_snapshot_statuses(conn: psycopg.Connection, *, profile_id: int, platform: str, limit: int = 3) -> list[str]` — most-recent-first list of `metrics->>'status'` values, used by the escalation-counting logic in Task 5.

- [ ] **Step 1: Write the failing tests**

Create `tests/store/test_analytics.py`:

```python
from __future__ import annotations

from claudeshorts.store import analytics
from claudeshorts.store import profiles as profiles_store


def _seed_profile(conn, slug="test-profile-1"):
    return profiles_store.upsert_profile(conn, slug=slug, display_name="Test Profile 1")


def test_insert_and_fetch_latest_snapshot(db_conn):
    profile_id = _seed_profile(db_conn)
    db_conn.commit()

    analytics.insert_snapshot(
        db_conn, profile_id=profile_id, platform="youtube",
        metrics={"status": "ok", "views": 100, "avg_view_duration_sec": 45.2},
    )
    db_conn.commit()

    latest = analytics.latest_snapshot(db_conn, profile_id=profile_id, platform="youtube")
    assert latest is not None
    assert latest["metrics"]["views"] == 100
    assert latest["platform"] == "youtube"


def test_latest_snapshot_returns_none_when_no_rows(db_conn):
    profile_id = _seed_profile(db_conn)
    db_conn.commit()

    assert analytics.latest_snapshot(db_conn, profile_id=profile_id, platform="youtube") is None


def test_recent_snapshot_statuses_most_recent_first(db_conn):
    profile_id = _seed_profile(db_conn)
    db_conn.commit()

    for status in ("ok", "error", "session_expired"):
        analytics.insert_snapshot(
            db_conn, profile_id=profile_id, platform="youtube", metrics={"status": status},
        )
        db_conn.commit()

    statuses = analytics.recent_snapshot_statuses(
        db_conn, profile_id=profile_id, platform="youtube", limit=3,
    )
    assert statuses == ["session_expired", "error", "ok"]


def test_recent_snapshot_statuses_respects_limit(db_conn):
    profile_id = _seed_profile(db_conn)
    db_conn.commit()

    for _ in range(5):
        analytics.insert_snapshot(
            db_conn, profile_id=profile_id, platform="youtube", metrics={"status": "error"},
        )
        db_conn.commit()

    statuses = analytics.recent_snapshot_statuses(
        db_conn, profile_id=profile_id, platform="youtube", limit=3,
    )
    assert len(statuses) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/store/test_analytics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'claudeshorts.store.analytics'`

- [ ] **Step 3: Write the implementation**

Create `claudeshorts/store/analytics.py`:

```python
"""Data-access helpers for the analytics_snapshots table (sub-project B).

One row per scrape attempt, success or failure — `metrics` always carries a
"status" key ("ok" | "session_expired" | "error") so callers can query
recent outcomes without a separate status column. See
services/analytics_service.py for what goes in `metrics` on success.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb


def insert_snapshot(
    conn: psycopg.Connection, *, profile_id: int, platform: str, metrics: dict[str, Any],
) -> int:
    row = conn.execute(
        "INSERT INTO analytics_snapshots (profile_id, platform, metrics) "
        "VALUES (%s, %s, %s) RETURNING id",
        (profile_id, platform, Jsonb(metrics)),
    ).fetchone()
    return int(row["id"])


def latest_snapshot(
    conn: psycopg.Connection, *, profile_id: int, platform: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM analytics_snapshots WHERE profile_id = %s AND platform = %s "
        "ORDER BY captured_at DESC LIMIT 1",
        (profile_id, platform),
    ).fetchone()
    return dict(row) if row else None


def recent_snapshot_statuses(
    conn: psycopg.Connection, *, profile_id: int, platform: str, limit: int = 3,
) -> list[str]:
    rows = conn.execute(
        "SELECT metrics->>'status' AS status FROM analytics_snapshots "
        "WHERE profile_id = %s AND platform = %s "
        "ORDER BY captured_at DESC LIMIT %s",
        (profile_id, platform, limit),
    ).fetchall()
    return [r["status"] for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/store/test_analytics.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Export from `store/__init__.py`**

In `claudeshorts/store/__init__.py`, add an import block matching the existing style (e.g. next to the `.profiles import (...)` block):

```python
from .analytics import insert_snapshot, latest_snapshot, recent_snapshot_statuses
```

And add the three names to the `__all__` list at the bottom of the file.

- [ ] **Step 6: Run the full store test suite to confirm nothing broke**

Run: `pytest tests/store/ -v`
Expected: all pass, no new failures

- [ ] **Step 7: Commit**

```bash
git add claudeshorts/store/analytics.py claudeshorts/store/__init__.py tests/store/test_analytics.py
git commit -m "feat: add store/analytics.py CRUD for analytics_snapshots"
```

---

### Task 3: Add `rebrowser-playwright` dependency + `browser/session.py` context helper

**Files:**
- Modify: `requirements.txt`
- Create: `claudeshorts/browser/session.py`
- Test: `tests/browser/test_session.py`

**Interfaces:**
- Consumes: `storage_state_path(slug: str) -> Path` from `claudeshorts/browser/profiles.py` (existing, line 56-57).
- Produces: `profile_browser_context(slug: str, *, headless: bool = True)` — a context manager yielding a Playwright `BrowserContext` (sync API) tied to that profile's stored login session. Task 5's `analytics_service.py` consumes this.

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, add this line after `psycopg[binary]>=3.2`:

```
rebrowser-playwright>=1.47
```

Install it:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

(The second command downloads the actual Chromium binary Playwright drives — `rebrowser-playwright` ships the same CLI entry point as `playwright`.)

- [ ] **Step 2: Write the failing test**

Create `tests/browser/test_session.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from claudeshorts.browser import session


def test_profile_browser_context_uses_storage_state_when_present(tmp_path, monkeypatch):
    state_file = tmp_path / "fork-ai" / "storage_state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text("{}")
    monkeypatch.setattr(session, "storage_state_path", lambda slug: state_file)

    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_playwright.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context

    with patch("claudeshorts.browser.session.sync_playwright") as mock_sp:
        mock_sp.return_value.__enter__.return_value = mock_playwright

        with session.profile_browser_context("fork-ai") as ctx:
            assert ctx is mock_context

    mock_browser.new_context.assert_called_once_with(storage_state=str(state_file))
    mock_context.close.assert_called_once()
    mock_browser.close.assert_called_once()


def test_profile_browser_context_omits_storage_state_when_missing(tmp_path, monkeypatch):
    missing_file = tmp_path / "midnight-curiosity" / "storage_state.json"
    monkeypatch.setattr(session, "storage_state_path", lambda slug: missing_file)

    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_playwright.chromium.launch.return_value = mock_browser

    with patch("claudeshorts.browser.session.sync_playwright") as mock_sp:
        mock_sp.return_value.__enter__.return_value = mock_playwright

        with session.profile_browser_context("midnight-curiosity"):
            pass

    mock_browser.new_context.assert_called_once_with(storage_state=None)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/browser/test_session.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'claudeshorts.browser.session'`

- [ ] **Step 4: Write the implementation**

Create `claudeshorts/browser/session.py`:

```python
"""Playwright browser-context helper scoped to a profile's stored login
session. Used by services/analytics_service.py to drive an authenticated
YouTube Studio session per profile, reusing the storage-state file
browser/profiles.py already tracks (browser/profiles.<slug>/storage_state.json)
rather than introducing a separate login/session system.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import BrowserContext, sync_playwright

from .profiles import storage_state_path


@contextmanager
def profile_browser_context(slug: str, *, headless: bool = True) -> Iterator[BrowserContext]:
    state_path = storage_state_path(slug)
    storage_state = str(state_path) if state_path.exists() else None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=storage_state)
        try:
            yield context
        finally:
            context.close()
            browser.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/browser/test_session.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt claudeshorts/browser/session.py tests/browser/test_session.py
git commit -m "feat: add rebrowser-playwright dependency and per-profile browser session helper"
```

---

### Task 4: Metric extraction — `_extract_youtube_metrics(page)`

**Files:**
- Create: `claudeshorts/services/analytics_service.py` (this task adds only the pure extraction function; Task 5 adds orchestration to the same file)
- Test: `tests/services/test_analytics_service.py`

**Interfaces:**
- Consumes: a Playwright `Page`-like object (duck-typed for testing — anything with `.locator(selector).inner_text()` and `.url`).
- Produces: `_extract_youtube_metrics(page) -> dict[str, float]` returning `{"avg_view_duration_sec": float, "retention_7s_pct": float, "views": float, "subscribers": float}`. Task 5's orchestration function consumes this.

This task isolates the DOM-parsing logic (the part most likely to break when YouTube's UI changes) so it's unit-testable without a real browser, per the spec's testing section.

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_analytics_service.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from claudeshorts.services import analytics_service


def _fake_page(values: dict[str, str]):
    page = MagicMock()

    def locator(selector):
        loc = MagicMock()
        loc.inner_text.return_value = values[selector]
        return loc

    page.locator.side_effect = locator
    return page


def test_extract_youtube_metrics_parses_numeric_values():
    page = _fake_page({
        analytics_service.SELECTOR_AVG_VIEW_DURATION: "0:45",
        analytics_service.SELECTOR_RETENTION_7S: "62.3%",
        analytics_service.SELECTOR_VIEWS: "4,200,000",
        analytics_service.SELECTOR_SUBSCRIBERS: "185,300",
    })

    metrics = analytics_service._extract_youtube_metrics(page)

    assert metrics == {
        "avg_view_duration_sec": 45.0,
        "retention_7s_pct": 62.3,
        "views": 4200000.0,
        "subscribers": 185300.0,
    }


def test_extract_youtube_metrics_parses_mm_ss_duration():
    page = _fake_page({
        analytics_service.SELECTOR_AVG_VIEW_DURATION: "3:45",
        analytics_service.SELECTOR_RETENTION_7S: "58.2%",
        analytics_service.SELECTOR_VIEWS: "100",
        analytics_service.SELECTOR_SUBSCRIBERS: "10",
    })

    metrics = analytics_service._extract_youtube_metrics(page)

    assert metrics["avg_view_duration_sec"] == 225.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_analytics_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'claudeshorts.services.analytics_service'`

- [ ] **Step 3: Write the implementation**

Create `claudeshorts/services/analytics_service.py`:

```python
"""YouTube Studio analytics scraping for sub-project B, Phase 1.

Retention/conversion metrics (average view duration, 7-second retention)
are treated as primary — views/subscribers are secondary, per the
deep-research finding that vanity metrics are too noisy at low sample
sizes to act on (see docs/superpowers/specs/2026-07-12-analytics-collection-design.md).

No route handler or CLI command should re-derive scraping/parsing logic —
this module is the single source of truth, same convention as
services/posts_service.py.
"""

from __future__ import annotations

# CSS selectors for YouTube Studio's Analytics > Overview tab. Kept as
# module constants (not inlined) so tests can target them without
# depending on YouTube's actual DOM, and so a future selector fix touches
# one line instead of a scattered literal.
SELECTOR_AVG_VIEW_DURATION = "[aria-label='Average view duration'] .ytcp-metric-value"
SELECTOR_RETENTION_7S = "[aria-label='Average percentage viewed'] .ytcp-metric-value"
SELECTOR_VIEWS = "[aria-label='Views'] .ytcp-metric-value"
SELECTOR_SUBSCRIBERS = "[aria-label='Subscribers'] .ytcp-metric-value"

YOUTUBE_STUDIO_ANALYTICS_URL = "https://studio.youtube.com/channel/analytics"


def _parse_duration_to_seconds(text: str) -> float:
    """'3:45' -> 225.0, '0:45' -> 45.0."""
    minutes, seconds = text.strip().split(":")
    return float(minutes) * 60 + float(seconds)


def _parse_number(text: str) -> float:
    """'4,200,000' -> 4200000.0, '62.3%' -> 62.3."""
    return float(text.strip().replace(",", "").replace("%", ""))


def _extract_youtube_metrics(page) -> dict[str, float]:
    return {
        "avg_view_duration_sec": _parse_duration_to_seconds(
            page.locator(SELECTOR_AVG_VIEW_DURATION).inner_text()
        ),
        "retention_7s_pct": _parse_number(page.locator(SELECTOR_RETENTION_7S).inner_text()),
        "views": _parse_number(page.locator(SELECTOR_VIEWS).inner_text()),
        "subscribers": _parse_number(page.locator(SELECTOR_SUBSCRIBERS).inner_text()),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_analytics_service.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/services/analytics_service.py tests/services/test_analytics_service.py
git commit -m "feat: add YouTube Studio metric-extraction logic"
```

---

### Task 5: Orchestration — `scrape_youtube_analytics(profile_id)` with error classification and escalation

**Files:**
- Modify: `claudeshorts/services/analytics_service.py` (add orchestration function to the file created in Task 4)
- Test: `tests/services/test_analytics_service.py` (append)

**Interfaces:**
- Consumes:
  - `_extract_youtube_metrics(page)` from Task 4.
  - `profile_browser_context(slug, *, headless=True)` from Task 3 (`claudeshorts.browser.session`).
  - `store.profiles.get_profile_by_id`, `store.analytics.insert_snapshot`, `store.analytics.recent_snapshot_statuses` (existing / Task 2).
  - `store.db.connect`.
  - `telegram_bot.notify.send_notification(text: str) -> None` (existing).
- Produces: `scrape_youtube_analytics(profile_id: int) -> dict` returning `{"status": "ok" | "session_expired" | "error", "detail": str | None}`. Task 6's job handler consumes this — it never raises for expected scrape-failure cases (auth expiry, transient error), only for genuine programming errors (e.g. profile not found), matching the spec's requirement that transient failures don't trigger the worker's generic on-exception Telegram alert.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/test_analytics_service.py`:

```python
from unittest.mock import patch

from claudeshorts.store import analytics as analytics_store
from claudeshorts.store import profiles as profiles_store


def _seed_profile(conn, slug="fork-ai"):
    return profiles_store.upsert_profile(conn, slug=slug, display_name="fork.ai")


def test_scrape_youtube_analytics_ok_path_inserts_snapshot(db_conn):
    profile_id = _seed_profile(db_conn)
    db_conn.commit()

    fake_metrics = {
        "avg_view_duration_sec": 225.0, "retention_7s_pct": 58.2,
        "views": 100.0, "subscribers": 10.0,
    }
    fake_page = MagicMock()
    fake_page.url = analytics_service.YOUTUBE_STUDIO_ANALYTICS_URL

    with patch(
        "claudeshorts.services.analytics_service.profile_browser_context"
    ) as mock_ctx, patch(
        "claudeshorts.services.analytics_service._extract_youtube_metrics",
        return_value=fake_metrics,
    ), patch("claudeshorts.services.analytics_service.send_notification") as mock_notify:
        mock_ctx.return_value.__enter__.return_value.new_page.return_value = fake_page

        result = analytics_service.scrape_youtube_analytics(profile_id)

    assert result == {"status": "ok", "detail": None}
    mock_notify.assert_not_called()

    from claudeshorts.store import db
    with db.connect() as conn:
        latest = analytics_store.latest_snapshot(conn, profile_id=profile_id, platform="youtube")
    assert latest["metrics"]["status"] == "ok"
    assert latest["metrics"]["views"] == 100.0


def test_scrape_youtube_analytics_session_expired_alerts_immediately(db_conn):
    profile_id = _seed_profile(db_conn)
    db_conn.commit()

    fake_page = MagicMock()
    fake_page.url = "https://accounts.google.com/signin"

    with patch(
        "claudeshorts.services.analytics_service.profile_browser_context"
    ) as mock_ctx, patch("claudeshorts.services.analytics_service.send_notification") as mock_notify:
        mock_ctx.return_value.__enter__.return_value.new_page.return_value = fake_page

        result = analytics_service.scrape_youtube_analytics(profile_id)

    assert result["status"] == "session_expired"
    mock_notify.assert_called_once()
    assert "fork-ai" in mock_notify.call_args[0][0]
    assert "session" in mock_notify.call_args[0][0].lower()

    from claudeshorts.store import db
    with db.connect() as conn:
        latest = analytics_store.latest_snapshot(conn, profile_id=profile_id, platform="youtube")
    assert latest["metrics"]["status"] == "session_expired"


def test_scrape_youtube_analytics_transient_error_no_alert_until_third_consecutive(db_conn):
    profile_id = _seed_profile(db_conn)
    db_conn.commit()

    with patch(
        "claudeshorts.services.analytics_service.profile_browser_context",
        side_effect=RuntimeError("navigation timeout"),
    ), patch("claudeshorts.services.analytics_service.send_notification") as mock_notify:
        result_1 = analytics_service.scrape_youtube_analytics(profile_id)
        result_2 = analytics_service.scrape_youtube_analytics(profile_id)
        result_3 = analytics_service.scrape_youtube_analytics(profile_id)

    assert [result_1["status"], result_2["status"], result_3["status"]] == ["error"] * 3
    mock_notify.assert_called_once()
    assert mock_notify.call_args[0][0].count("fork-ai") >= 1


def test_scrape_youtube_analytics_raises_for_unknown_profile():
    import pytest

    with pytest.raises(ValueError, match="no profile"):
        analytics_service.scrape_youtube_analytics(999999)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_analytics_service.py -v`
Expected: FAIL with `AttributeError: module 'claudeshorts.services.analytics_service' has no attribute 'scrape_youtube_analytics'` (and `profile_browser_context`/`send_notification` not yet imported into the module)

- [ ] **Step 3: Write the implementation**

Append to `claudeshorts/services/analytics_service.py` (after the existing imports at the top, add these two imports; then add the new function at the end of the file):

Add to the top of the file, after the module docstring:

```python
from ..browser.session import profile_browser_context
from ..store import analytics as analytics_store
from ..store import db
from ..store.profiles import get_profile_by_id
from ..telegram_bot.notify import send_notification

TRANSIENT_ERROR_ESCALATION_THRESHOLD = 3
```

Add at the end of the file:

```python
def scrape_youtube_analytics(profile_id: int) -> dict[str, str | None]:
    """Scrape one profile's YouTube Studio analytics and record the
    outcome. Never raises for expected failure modes (auth expiry,
    transient scrape errors) — only for a genuinely missing profile, which
    is a caller bug, not a scrape-time condition. This is deliberate: the
    job worker's generic on-exception handler (jobs/worker.py) sends a
    Telegram alert for *any* raised exception, which would spam on every
    transient scrape hiccup. Alerting here is instead explicit and
    status-driven, per docs/superpowers/specs/2026-07-12-analytics-collection-design.md.
    """
    with db.connect() as conn:
        profile = get_profile_by_id(conn, profile_id)
    if profile is None:
        raise ValueError(f"no profile with id {profile_id}")
    slug = profile["slug"]

    try:
        with profile_browser_context(slug) as context:
            page = context.new_page()
            page.goto(YOUTUBE_STUDIO_ANALYTICS_URL)

            if "accounts.google.com" in page.url:
                return _record_session_expired(profile_id, slug)

            metrics = _extract_youtube_metrics(page)
    except Exception as exc:  # noqa: BLE001 - any scrape failure is "transient" here
        return _record_transient_error(profile_id, slug, exc)

    with db.connect() as conn:
        analytics_store.insert_snapshot(
            conn, profile_id=profile_id, platform="youtube",
            metrics={"status": "ok", **metrics},
        )
    return {"status": "ok", "detail": None}


def _record_session_expired(profile_id: int, slug: str) -> dict[str, str | None]:
    with db.connect() as conn:
        analytics_store.insert_snapshot(
            conn, profile_id=profile_id, platform="youtube",
            metrics={"status": "session_expired"},
        )
    detail = f"YouTube session expired for profile {slug} — re-login required in the browser profile."
    send_notification(detail)
    return {"status": "session_expired", "detail": detail}


def _record_transient_error(profile_id: int, slug: str, exc: Exception) -> dict[str, str | None]:
    with db.connect() as conn:
        analytics_store.insert_snapshot(
            conn, profile_id=profile_id, platform="youtube",
            metrics={"status": "error", "error": str(exc)},
        )
        recent = analytics_store.recent_snapshot_statuses(
            conn, profile_id=profile_id, platform="youtube",
            limit=TRANSIENT_ERROR_ESCALATION_THRESHOLD,
        )

    detail = f"YouTube analytics scrape failed for profile {slug}: {exc}"
    if len(recent) == TRANSIENT_ERROR_ESCALATION_THRESHOLD and all(s == "error" for s in recent):
        send_notification(
            f"YouTube analytics scrape has failed {TRANSIENT_ERROR_ESCALATION_THRESHOLD} "
            f"times in a row for profile {slug}. Latest error: {exc}"
        )
    return {"status": "error", "detail": detail}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_analytics_service.py -v`
Expected: PASS (6 tests total: 2 from Task 4, 4 new)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/services/analytics_service.py tests/services/test_analytics_service.py
git commit -m "feat: add scrape_youtube_analytics orchestration with session-expiry and escalation alerting"
```

---

### Task 6: Wire into the job registry

**Files:**
- Modify: `claudeshorts/jobs/registry.py`
- Test: `tests/jobs/test_registry.py` (append)

**Interfaces:**
- Consumes: `analytics_service.scrape_youtube_analytics(profile_id: int) -> dict` from Task 5.
- Produces: `JOB_HANDLERS["scrape_analytics"]` — consumed by Task 7's scheduler seeding (via the `job_type` string `"scrape_analytics"`, not `analytics_service` directly).

- [ ] **Step 1: Write the failing test**

Append to `tests/jobs/test_registry.py`:

```python
def test_scrape_analytics_job_threads_profile_id_from_payload():
    with patch(
        "claudeshorts.services.analytics_service.scrape_youtube_analytics"
    ) as mock_fn:
        mock_fn.return_value = {"status": "ok", "detail": None}
        result = registry.JOB_HANDLERS["scrape_analytics"]({"profile_id": 7})
        mock_fn.assert_called_once_with(7)
        assert result == {"status": "ok", "detail": None}
```

Also update the existing `test_all_six_job_types_registered` test (despite its name, it currently checks 5) to include the new type — find it and change the expected set:

```python
def test_all_job_types_registered():
    expected = {
        "full_run", "ingest", "generate", "generate_from_item", "render_post",
        "drain_scheduled_posts", "weekly_report", "scrape_analytics",
    }
    assert expected <= set(registry.JOB_HANDLERS)
```

(Rename `test_all_six_job_types_registered` to `test_all_job_types_registered` since the count is now stale either way — this is a pre-existing naming drift, not something introduced by this task, but it should be fixed while touching this test.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/jobs/test_registry.py -v`
Expected: FAIL — `KeyError: 'scrape_analytics'`

- [ ] **Step 3: Write the implementation**

In `claudeshorts/jobs/registry.py`, add the import at the top (alongside the existing `from ..services import pipeline_service, reporting_service`):

```python
from ..services import analytics_service, pipeline_service, reporting_service
```

Add this line after the existing `JOB_HANDLERS["weekly_report"] = ...` line at the bottom of the file:

```python
JOB_HANDLERS["scrape_analytics"] = lambda payload: analytics_service.scrape_youtube_analytics(
    payload["profile_id"]
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/jobs/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/jobs/registry.py tests/jobs/test_registry.py
git commit -m "feat: register scrape_analytics job type"
```

---

### Task 7: Seed a daily `scrape_analytics:<slug>` schedule per active profile

**Files:**
- Modify: `claudeshorts/scheduling/scheduler.py`
- Modify: `config/settings.yaml`
- Test: `tests/scheduling/test_scheduler.py` (append)

**Interfaces:**
- Consumes: `sched_store.upsert_schedule(...)` (existing), `"scrape_analytics"` job type from Task 6.
- Produces: a `scrape_analytics:<slug>` row in `schedules` per active profile, ticked by the existing `scheduler.tick()` — no new consumer needed, this closes the loop back to Task 6's job handler.

- [ ] **Step 1: Add a config knob**

In `config/settings.yaml`, add a new line to the `schedule:` block (after `weekly_report_time: "09:00"`):

```yaml
  analytics_scrape_time: "07:00"  # HH:MM local time for the daily YouTube analytics scrape, before the daily_run_time full_run
```

- [ ] **Step 2: Write the failing test**

Append to `tests/scheduling/test_scheduler.py` — match the existing test file's imports and fixture usage (it already imports `scheduler`, `profiles_store`, `db`, uses `db_conn`):

```python
def test_seed_default_schedules_creates_scrape_analytics_schedule(db_conn):
    profiles_store.upsert_profile(db_conn, slug="fork-ai", display_name="fork.ai")
    db_conn.commit()

    scheduler.seed_default_schedules()

    from claudeshorts.store import db as store_db
    with store_db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM schedules WHERE name = %s", ("scrape_analytics:fork-ai",)
        ).fetchone()

    assert row is not None
    assert row["job_type"] == "scrape_analytics"
    assert row["payload"] == {"profile_id": 1}
    assert row["kind"] == "daily_at"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/scheduling/test_scheduler.py::test_seed_default_schedules_creates_scrape_analytics_schedule -v`
Expected: FAIL — the `scrape_analytics:fork-ai` row doesn't exist (`row is None`, `assert row is not None` fails)

- [ ] **Step 4: Write the implementation**

In `claudeshorts/scheduling/scheduler.py`, inside `seed_default_schedules()`, add this line near the top with the other cadence reads:

```python
    analytics_scrape_at = cfg.get("analytics_scrape_time", "07:00")
```

Then inside the `for profile in active_profiles:` loop, after the existing `weekly_report` `upsert_schedule` call, add:

```python
            sched_store.upsert_schedule(
                f"scrape_analytics:{slug}", "scrape_analytics", payload, "daily_at",
                daily_at=analytics_scrape_at,
                initial_next_run_at=next_run_at(
                    "daily_at", daily_at=analytics_scrape_at, after=now,
                ),
                conn=conn,
            )
```

Also update the docstring of `seed_default_schedules()` to mention the new schedule type, since it currently says "Seed one full_run/drain_scheduled_posts/weekly_report schedule per active profile" — change to "Seed one full_run/drain_scheduled_posts/weekly_report/scrape_analytics schedule per active profile."

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/scheduling/test_scheduler.py -v`
Expected: PASS — including the pre-existing tests that check the full set of seeded schedule names (e.g. a test iterating `("full_run:fork-ai", "drain_scheduled_posts:fork-ai", "weekly_report:fork-ai")` — check whether that literal tuple needs `"scrape_analytics:fork-ai"` added too; if a test asserts an exact set/count of schedules rather than a subset, update it the same way Task 6 updated `test_all_six_job_types_registered`)

- [ ] **Step 6: Run the full scheduling test suite**

Run: `pytest tests/scheduling/ -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add claudeshorts/scheduling/scheduler.py config/settings.yaml tests/scheduling/test_scheduler.py
git commit -m "feat: seed daily scrape_analytics schedule per active profile"
```

---

### Task 8: Live verification against a real YouTube Studio session

**Files:**
- None created — this is a manual verification task, per the spec's testing section ("do not attempt to unit-test against a live scrape in CI").

**Interfaces:**
- Consumes: everything from Tasks 1-7, plus a real logged-in browser profile.

- [ ] **Step 1: Ensure at least one profile has a real YouTube login session**

Check whether `browser/profiles/<slug>/storage_state.json` exists for the `fork-ai` profile (the storage-state path Task 3's `profile_browser_context` reads from):

```bash
ls "$(python3 -c "from claudeshorts.browser.profiles import storage_state_path; print(storage_state_path('fork-ai'))")"
```

If it doesn't exist, this requires a one-time interactive login — write a small throwaway script (not committed) that opens a headed (non-headless) Playwright browser to `https://studio.youtube.com`, lets you log in by hand, then calls `context.storage_state(path=...)` to save it to that path. This is a manual, human-in-the-loop step — do not attempt to automate YouTube login itself.

- [ ] **Step 2: Run a real scrape**

```bash
python3 -c "
from claudeshorts.store.profiles import get_profile
from claudeshorts.store import db
from claudeshorts.services.analytics_service import scrape_youtube_analytics
with db.connect() as conn:
    profile = get_profile(conn, 'fork-ai')
print(scrape_youtube_analytics(profile['id']))
"
```

Expected: `{'status': 'ok', 'detail': None}` (or `session_expired` if the storage state from Step 1 wasn't valid — re-check login in that case).

- [ ] **Step 3: Confirm the scraped values look right by eye**

```bash
python3 -c "
from claudeshorts.store.profiles import get_profile
from claudeshorts.store.analytics import latest_snapshot
from claudeshorts.store import db
with db.connect() as conn:
    profile = get_profile(conn, 'fork-ai')
    print(latest_snapshot(conn, profile_id=profile['id'], platform='youtube'))
"
```

Open YouTube Studio's Analytics tab in a real browser tab for the same channel side by side, and confirm `avg_view_duration_sec`, `retention_7s_pct`, `views`, `subscribers` roughly match what's shown in the UI (exact match isn't expected if time has passed between the scrape and the manual check, but they should be in the same ballpark).

- [ ] **Step 4: Confirm session-expiry alerting works end-to-end (optional but recommended)**

Temporarily corrupt the storage state file (e.g. `echo '{}' > <storage_state_path>`) and re-run Step 2 — confirm the result is `{'status': 'session_expired', ...}` and that a Telegram message actually arrives (requires `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` set in `.env`). Restore the real storage state file afterward (re-do Step 1's login if you overwrote it).

- [ ] **Step 5: No commit needed — this task is verification only**

If Steps 2-4 reveal a bug (e.g. selectors don't match YouTube Studio's actual current DOM — likely, since Task 4's selectors are best-guess placeholders for YouTube Studio's aria-label structure and YouTube's DOM changes without notice), fix `SELECTOR_*` constants in `claudeshorts/services/analytics_service.py` directly against the real page (use browser devtools to find the actual selectors), re-run the existing unit tests to confirm they still pass (they mock the page, so selector changes don't break them — only Step 2 catches selector drift), then commit the selector fix:

```bash
git add claudeshorts/services/analytics_service.py
git commit -m "fix: correct YouTube Studio analytics selectors against real DOM"
```

---

## Self-Review Notes

**Spec coverage:** Phase 1/YouTube-only scope (Task 4-8 all YouTube-specific, no Instagram/TikTok code added) ✓. Daily scrape via existing scheduler pattern (Task 7) ✓. `rebrowser-playwright` + existing per-profile session storage, no new login system (Task 3) ✓. New dedicated `analytics_snapshots` table, not extending `runs` (Task 1) ✓. Retention/conversion metrics as primary fields (Task 4's `_extract_youtube_metrics`) ✓. vidIQ MCP as bonus source — **not included in this plan**; the spec calls it a bonus/additive source, not a Phase 1 requirement, so it's deferred to a follow-up task rather than blocking this plan (flagging explicitly here since it's a spec line without a corresponding task). Session-expiry alerts via both Telegram and a queryable DB status (Task 5) ✓. Transient errors don't alert until 3 consecutive failures (Task 5) ✓. Mocked unit tests only, live verification as a separate manual task (Task 8) ✓.

**Placeholder scan:** no TBD/TODO markers; the one soft value (`TRANSIENT_ERROR_ESCALATION_THRESHOLD = 3`) is a named constant with a comment pointing at its source, not a placeholder — matches the spec's explicit note that this default is adjustable.

**Type consistency:** `scrape_youtube_analytics(profile_id: int) -> dict[str, str | None]` (Task 5) matches how Task 6's job handler calls it (`analytics_service.scrape_youtube_analytics(payload["profile_id"])`) and what it returns (`{"status": ..., "detail": ...}`, consumed as the job's `result` by `jobs/worker.py`'s existing `str(result)` handling — no changes needed there). `insert_snapshot`/`latest_snapshot`/`recent_snapshot_statuses` signatures in Task 2 match every call site in Task 5. `profile_browser_context(slug, *, headless=True)` in Task 3 matches its only call site in Task 5.
