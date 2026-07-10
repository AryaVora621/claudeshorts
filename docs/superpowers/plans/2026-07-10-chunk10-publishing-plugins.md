# Chunk 10: Publishing Plugins + Multi-Channel Posting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single hardcoded channel + hand-copied per-platform export with a `PublishProvider` plugin interface (folder-export always available, per-platform API stubs ready for real credentials) and a real multi-channel data model (`channels` table, `posts.channel_id`, deterministic channel routing).

**Architecture:** New `claudeshorts/publish/providers/` package (Protocol + `FolderExportProvider` + three credential-gated API stub providers + registry); new `claudeshorts/publish/channel_rules.py` (pure function, same shape as chunk 8's `style_rules.select_layout`); new `claudeshorts/store/channels.py`; `posts` table gains `channel_id`; `render/bridge.py` and `publish/exporter.py` become channel-aware.

**Tech Stack:** Python 3.11+, existing SQLite store layer (Postgres dialect per chunk 1, once that chunk lands — this plan writes SQLite-compatible SQL matching today's actual `store/db.py`).

## Global Constraints

- No comments explaining *what*, only non-obvious *why*.
- `channel_rules.py` and provider `publish()` implementations must not make real network calls in this chunk — API providers only validate credentials presence and raise a clear error otherwise.
- **This repository currently has no `tests/` directory at all** — every test file below is a genuinely new file (not an extension of an existing one, despite the pattern used in earlier chunks' plans). Each Task 1 step must also create a minimal `tests/conftest.py` fixture if one doesn't yet exist from an earlier-executed chunk's plan (check first — the DB fixture only needs to exist once).
- Full spec: `docs/superpowers/specs/2026-07-10-chunk10-publishing-plugins-design.md`.

---

## File Structure

- Create: `claudeshorts/publish/providers/__init__.py`, `base.py`, `folder_export.py`, `youtube_api.py`, `tiktok_api.py`, `instagram_api.py`, `registry.py`
- Create: `claudeshorts/publish/channel_rules.py`
- Create: `claudeshorts/store/channels.py`
- Modify: `claudeshorts/store/db.py`, `claudeshorts/store/__init__.py`, `claudeshorts/generate/runner.py`, `claudeshorts/render/bridge.py`, `claudeshorts/publish/exporter.py`, `config/settings.yaml`
- Test: `tests/conftest.py` (if not already present), `tests/store/test_channels.py`, `tests/publish/test_channel_rules.py`, `tests/publish/providers/test_folder_export.py`, `tests/publish/providers/test_api_stubs.py`, `tests/publish/providers/test_registry.py`

---

### Task 1: `tests/conftest.py` DB fixture (create if absent) + `channels` table + `store/channels.py`

**Files:**
- Create (if absent): `tests/conftest.py`
- Modify: `claudeshorts/store/db.py`
- Create: `claudeshorts/store/channels.py`
- Modify: `claudeshorts/store/__init__.py`
- Test: `tests/store/test_channels.py`

**Interfaces:**
- Produces: `store.channels.insert_channel(conn, *, slug, name, handle=None, logo=None, enabled=True) -> int`, `get_channel(conn, channel_id) -> dict | None`, `get_by_slug(conn, slug) -> dict | None`, `list_enabled_channels(conn) -> list[dict]`.

- [ ] **Step 1: Check for and create the shared test DB fixture**

Run: `test -f tests/conftest.py && echo EXISTS || echo MISSING`

If `MISSING`, create it:

```python
# tests/conftest.py
from __future__ import annotations

import sqlite3

import pytest

from claudeshorts.store.db import SCHEMA, _apply_migrations


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _apply_migrations(conn)
    yield conn
    conn.close()
```

If it already exists (created by an earlier-executed chunk plan), skip
this step and reuse it as-is.

- [ ] **Step 2: Write the failing test**

```python
# tests/store/test_channels.py
from __future__ import annotations

from claudeshorts.store import channels


def test_insert_and_get_channel(db):
    channel_id = channels.insert_channel(db, slug="midnight-curiosity", name="Midnight Curiosity", handle="@midnight.curiosity")
    row = channels.get_channel(db, channel_id)
    assert row["slug"] == "midnight-curiosity"
    assert row["name"] == "Midnight Curiosity"
    assert row["enabled"] == 1


def test_get_by_slug():
    pass  # placeholder removed below — see Step 3's real version


def test_get_by_slug_real(db):
    channels.insert_channel(db, slug="robotics-daily", name="Robotics Daily")
    row = channels.get_by_slug(db, "robotics-daily")
    assert row is not None
    assert row["name"] == "Robotics Daily"


def test_get_by_slug_missing_returns_none(db):
    assert channels.get_by_slug(db, "nonexistent") is None


def test_list_enabled_channels_excludes_disabled(db):
    channels.insert_channel(db, slug="a", name="A", enabled=True)
    channels.insert_channel(db, slug="b", name="B", enabled=False)
    enabled = channels.list_enabled_channels(db)
    assert [c["slug"] for c in enabled] == ["a"]
```

Remove the placeholder `test_get_by_slug` stub before running — it exists
in this plan only to flag that the real assertion is `test_get_by_slug_real`
immediately below it; do not implement the empty placeholder version.

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/store/test_channels.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.store.channels'`

- [ ] **Step 4: Add the `channels` table to `db.py`**

In `SCHEMA` (`claudeshorts/store/db.py`), add after the `items` table
definition:

```sql
CREATE TABLE IF NOT EXISTS channels (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    slug     TEXT NOT NULL UNIQUE,
    name     TEXT NOT NULL,
    handle   TEXT,
    logo     TEXT,
    enabled  INTEGER NOT NULL DEFAULT 1
);
```

Add `("posts", "channel_id", "INTEGER REFERENCES channels(id)")` to
`_MIGRATIONS` (after the existing `scheduled_for` entry).

- [ ] **Step 5: Implement `store/channels.py`**

```python
"""Data-access helpers for the `channels` table (multi-channel identity)."""

from __future__ import annotations

import sqlite3
from typing import Any


def insert_channel(
    conn: sqlite3.Connection, *, slug: str, name: str,
    handle: str | None = None, logo: str | None = None, enabled: bool = True,
) -> int:
    cur = conn.execute(
        "INSERT INTO channels (slug, name, handle, logo, enabled) VALUES (?, ?, ?, ?, ?)",
        (slug, name, handle, logo, int(enabled)),
    )
    return int(cur.lastrowid)


def get_channel(conn: sqlite3.Connection, channel_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    return dict(row) if row else None


def get_by_slug(conn: sqlite3.Connection, slug: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM channels WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def list_enabled_channels(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM channels WHERE enabled = 1 ORDER BY id").fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 6: Update `store/__init__.py` exports**

Add to the import block and `__all__`:

```python
from .channels import get_by_slug, get_channel, insert_channel, list_enabled_channels
```
and the four names to `__all__`.

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/store/test_channels.py -v`
Expected: PASS (4 tests — after removing the placeholder stub per Step 2's note)

- [ ] **Step 8: Commit**

```bash
git add tests/conftest.py claudeshorts/store/db.py claudeshorts/store/channels.py claudeshorts/store/__init__.py tests/store/test_channels.py
git commit -m "feat: add channels table and store.channels data-access module"
```

---

### Task 2: `channel_rules.py` — deterministic channel routing

**Files:**
- Create: `claudeshorts/publish/channel_rules.py`
- Test: `tests/publish/test_channel_rules.py`

**Interfaces:**
- Produces: `select_channel(item: dict, channel_rules: dict, default_channel: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/publish/test_channel_rules.py
from __future__ import annotations

from claudeshorts.publish.channel_rules import select_channel

RULES = {"robotics-daily": ["robot", "boston dynamics"]}


def test_select_channel_matches_keyword_in_title():
    item = {"title": "Boston Dynamics unveils new robot", "summary": ""}
    assert select_channel(item, RULES, "midnight-curiosity") == "robotics-daily"


def test_select_channel_matches_keyword_in_summary():
    item = {"title": "Big update today", "summary": "a new robot arm design"}
    assert select_channel(item, RULES, "midnight-curiosity") == "robotics-daily"


def test_select_channel_no_match_returns_default():
    item = {"title": "OpenAI ships GPT-5.5", "summary": ""}
    assert select_channel(item, RULES, "midnight-curiosity") == "midnight-curiosity"


def test_select_channel_empty_rules_returns_default():
    assert select_channel({"title": "anything"}, {}, "midnight-curiosity") == "midnight-curiosity"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/publish/test_channel_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.publish.channel_rules'`

- [ ] **Step 3: Implement `channel_rules.py`**

```python
"""Deterministic channel routing — same first-match-in-insertion-order
shape as generate/style_rules.py's select_layout, so a second channel with
real topic focus can be added via config alone, no code change."""

from __future__ import annotations


def select_channel(item: dict, channel_rules: dict, default_channel: str) -> str:
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    for slug, keywords in channel_rules.items():
        if any(kw.lower() in haystack for kw in keywords):
            return slug
    return default_channel
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/publish/test_channel_rules.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/publish/channel_rules.py tests/publish/test_channel_rules.py
git commit -m "feat: add deterministic channel routing rules"
```

---

### Task 3: `PublishProvider` base + `FolderExportProvider`

**Files:**
- Create: `claudeshorts/publish/providers/__init__.py` (empty)
- Create: `claudeshorts/publish/providers/base.py`
- Create: `claudeshorts/publish/providers/folder_export.py`
- Test: `tests/publish/providers/test_folder_export.py`

**Interfaces:**
- Produces: `PublishProvider` Protocol (`publish(post, platform, channel) -> dict`), `FolderExportProvider().publish(post, platform, channel)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/publish/providers/test_folder_export.py
from __future__ import annotations

from pathlib import Path

from claudeshorts.publish.providers.folder_export import FolderExportProvider


def _make_rendered_post(tmp_path, monkeypatch, post_id=1):
    import claudeshorts.config as config
    monkeypatch.setattr(config, "RENDERS_DIR", tmp_path / "renders")
    monkeypatch.setattr(config, "PUBLISH_DIR", tmp_path / "publish")
    render_dir = config.RENDERS_DIR / f"post_{post_id}"
    render_dir.mkdir(parents=True)
    (render_dir / "video.mp4").write_bytes(b"fake-mp4")
    return config


def test_publish_copies_video_and_caption_into_channel_scoped_path(tmp_path, monkeypatch):
    config = _make_rendered_post(tmp_path, monkeypatch)
    post = {"id": 1, "captions": {"youtube": {"title": "T", "description": "D", "hashtags": []}}}
    channel = {"slug": "midnight-curiosity"}
    provider = FolderExportProvider()

    result = provider.publish(post, "youtube", channel)

    dest = Path(result["location"])
    assert dest.exists()
    assert "midnight-curiosity" in str(dest)
    assert (dest / "video.mp4").exists()
    assert (dest / "caption.txt").exists()
    assert result["status"] == "exported"


def test_publish_raises_if_video_not_rendered(tmp_path, monkeypatch):
    import claudeshorts.config as config
    monkeypatch.setattr(config, "RENDERS_DIR", tmp_path / "renders")
    monkeypatch.setattr(config, "PUBLISH_DIR", tmp_path / "publish")
    provider = FolderExportProvider()
    import pytest
    with pytest.raises(FileNotFoundError):
        provider.publish({"id": 99, "captions": {}}, "youtube", {"slug": "midnight-curiosity"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/publish/providers/test_folder_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.publish.providers.folder_export'`

- [ ] **Step 3: Implement `base.py` and `folder_export.py`**

```python
# claudeshorts/publish/providers/base.py
"""Every publish provider implements this. `status` distinguishes an
assisted folder-drop (human still uploads) from a future provider that
completes the upload itself."""

from __future__ import annotations

from typing import Protocol


class PublishProvider(Protocol):
    def publish(self, post: dict, platform: str, channel: dict) -> dict: ...
```

```python
# claudeshorts/publish/providers/folder_export.py
"""Assisted export: copy the rendered MP4 + carousel stills + a formatted
caption into publish/<channel_slug>/<platform>/<date>/post_<id>/. Moved
from publish/exporter.py's per-platform loop (chunk 10 extraction) and
made channel-scoped so multiple channels' exports never collide."""

from __future__ import annotations

import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ... import config
from ...review.captions import PLATFORM_CAPTION
from ...review.queue import review_dir_for


class FolderExportProvider:
    def publish(self, post: dict[str, Any], platform: str, channel: dict[str, Any]) -> dict[str, Any]:
        video = self._locate_video(post["id"])
        slides = self._locate_slides(post["id"])
        today = date.today().isoformat()
        dest = config.PUBLISH_DIR / channel["slug"] / platform / today / f"post_{post['id']}"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(video, dest / "video.mp4")
        if slides:
            slides_dest = dest / "slides"
            slides_dest.mkdir(parents=True, exist_ok=True)
            for still in slides:
                shutil.copy2(still, slides_dest / still.name)
        formatter = PLATFORM_CAPTION.get(platform)
        text = formatter(post.get("captions") or {}) if formatter else ""
        (dest / "caption.txt").write_text(text + "\n", encoding="utf-8")
        return {
            "status": "exported",
            "location": str(dest),
            "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def _locate_video(self, post_id: int) -> Path:
        candidate = review_dir_for(post_id) / "video.mp4"
        if candidate.exists():
            return candidate
        fallback = config.RENDERS_DIR / f"post_{post_id}" / "video.mp4"
        if fallback.exists():
            return fallback
        raise FileNotFoundError(
            f"no rendered video for post {post_id} — render it before exporting."
        )

    def _locate_slides(self, post_id: int) -> list[Path]:
        for base in (review_dir_for(post_id) / "slides",
                     config.RENDERS_DIR / f"post_{post_id}" / "slides"):
            if base.is_dir():
                stills = sorted(base.glob("slide_*.png"))
                if stills:
                    return stills
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/publish/providers/test_folder_export.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/publish/providers/__init__.py claudeshorts/publish/providers/base.py claudeshorts/publish/providers/folder_export.py tests/publish/providers/test_folder_export.py
git commit -m "feat: extract PublishProvider protocol and channel-scoped FolderExportProvider"
```

---

### Task 4: API stub providers (`youtube_api`, `tiktok_api`, `instagram_api`) + registry

**Files:**
- Create: `claudeshorts/publish/providers/youtube_api.py`, `tiktok_api.py`, `instagram_api.py`, `registry.py`
- Test: `tests/publish/providers/test_api_stubs.py`, `tests/publish/providers/test_registry.py`

**Interfaces:**
- Produces: `YouTubeAPIProvider(credentials_env: str)`, `TikTokAPIProvider(credentials_env: str)`, `InstagramAPIProvider(credentials_env: str)`, each `.publish(post, platform, channel)`; `get_provider(name: str, *, credentials_env: str | None = None) -> PublishProvider`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/publish/providers/test_api_stubs.py
from __future__ import annotations

import pytest

from claudeshorts.publish.providers.youtube_api import YouTubeAPIProvider
from claudeshorts.publish.providers.tiktok_api import TikTokAPIProvider
from claudeshorts.publish.providers.instagram_api import InstagramAPIProvider


@pytest.mark.parametrize("cls,platform", [
    (YouTubeAPIProvider, "youtube"),
    (TikTokAPIProvider, "tiktok"),
    (InstagramAPIProvider, "instagram"),
])
def test_publish_raises_when_credentials_env_unset(cls, platform, monkeypatch):
    monkeypatch.delenv("FAKE_CREDS_VAR", raising=False)
    provider = cls(credentials_env="FAKE_CREDS_VAR")
    with pytest.raises(RuntimeError, match="no .* credentials configured"):
        provider.publish({"id": 1, "captions": {}}, platform, {"slug": "midnight-curiosity"})


@pytest.mark.parametrize("cls", [YouTubeAPIProvider, TikTokAPIProvider, InstagramAPIProvider])
def test_publish_does_not_raise_credentials_error_when_env_set(cls, monkeypatch):
    monkeypatch.setenv("FAKE_CREDS_VAR", "some-fake-value")
    provider = cls(credentials_env="FAKE_CREDS_VAR")
    with pytest.raises(NotImplementedError):
        provider.publish({"id": 1, "captions": {}}, "youtube", {"slug": "midnight-curiosity"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/publish/providers/test_api_stubs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.publish.providers.youtube_api'`

- [ ] **Step 3: Implement the three API stub providers**

```python
# claudeshorts/publish/providers/youtube_api.py
"""Real interface, no live network call yet — the code path exists and
works the moment a channel has real YouTube Data API credentials (chunk
10's final, human-required task). Until then it fails loudly and
specifically rather than silently no-opping."""

from __future__ import annotations

import os
from typing import Any


class YouTubeAPIProvider:
    def __init__(self, credentials_env: str):
        self.credentials_env = credentials_env

    def publish(self, post: dict[str, Any], platform: str, channel: dict[str, Any]) -> dict[str, Any]:
        if not os.environ.get(self.credentials_env):
            raise RuntimeError(
                f"channel '{channel['slug']}' has no {platform} credentials configured — "
                f"set {self.credentials_env} or use provider: folder_export"
            )
        raise NotImplementedError(
            "YouTube Data API upload not yet implemented — chunk 10's final task, "
            "blocked on real OAuth app registration."
        )
```

`tiktok_api.py` and `instagram_api.py` are identical apart from the class
name and the docstring's platform name (`TikTokAPIProvider` /
`InstagramAPIProvider`, `"TikTok Content Posting API"` /
`"Instagram Graph API"` in the `NotImplementedError` message).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/publish/providers/test_api_stubs.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Write the failing registry test**

```python
# tests/publish/providers/test_registry.py
from __future__ import annotations

import pytest

from claudeshorts.publish.providers import registry
from claudeshorts.publish.providers.folder_export import FolderExportProvider
from claudeshorts.publish.providers.youtube_api import YouTubeAPIProvider


def test_get_provider_folder_export():
    assert isinstance(registry.get_provider("folder_export"), FolderExportProvider)


def test_get_provider_youtube_api_requires_credentials_env():
    provider = registry.get_provider("youtube_api", credentials_env="YT_CREDS")
    assert isinstance(provider, YouTubeAPIProvider)
    assert provider.credentials_env == "YT_CREDS"


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError, match="unknown publish provider"):
        registry.get_provider("not-a-real-provider")
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/publish/providers/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.publish.providers.registry'`

- [ ] **Step 7: Implement `registry.py`**

```python
"""Maps a channel platform config's `provider` name to a live instance."""

from __future__ import annotations

from typing import Any

from .folder_export import FolderExportProvider
from .instagram_api import InstagramAPIProvider
from .tiktok_api import TikTokAPIProvider
from .youtube_api import YouTubeAPIProvider


def get_provider(name: str, *, credentials_env: str | None = None) -> Any:
    if name == "folder_export":
        return FolderExportProvider()
    if name == "youtube_api":
        return YouTubeAPIProvider(credentials_env=credentials_env or "YOUTUBE_API_CREDENTIALS_JSON")
    if name == "tiktok_api":
        return TikTokAPIProvider(credentials_env=credentials_env or "TIKTOK_API_CREDENTIALS_JSON")
    if name == "instagram_api":
        return InstagramAPIProvider(credentials_env=credentials_env or "INSTAGRAM_API_CREDENTIALS_JSON")
    raise ValueError(f"unknown publish provider: {name!r} (use folder_export|youtube_api|tiktok_api|instagram_api)")
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/publish/providers/test_registry.py -v`
Expected: PASS (3 tests)

- [ ] **Step 9: Commit**

```bash
git add claudeshorts/publish/providers/youtube_api.py claudeshorts/publish/providers/tiktok_api.py claudeshorts/publish/providers/instagram_api.py claudeshorts/publish/providers/registry.py tests/publish/providers/test_api_stubs.py tests/publish/providers/test_registry.py
git commit -m "feat: add credential-gated API stub providers + publish provider registry"
```

---

### Task 5: Wire channels into config, generation, rendering, and export

**Files:**
- Modify: `config/settings.yaml`
- Modify: `claudeshorts/generate/runner.py`
- Modify: `claudeshorts/render/bridge.py`
- Modify: `claudeshorts/publish/exporter.py`

**Interfaces:**
- Consumes: `channel_rules.select_channel`, `store.channels.get_by_slug`, `publish.providers.registry.get_provider`.
- Produces: `posts.channel_id` populated at generation time; `build_spec` uses the post's linked channel; `export_post` iterates the channel's configured platforms via the registry.

- [ ] **Step 1: Replace `config/settings.yaml`'s `channel:` block**

```yaml
channels:
  - slug: midnight-curiosity
    name: "Midnight Curiosity"
    handle: "@midnight.curiosity"
    logo: "assets/logo.png"
    enabled: true
    platforms:
      youtube:   {provider: folder_export}
      tiktok:    {provider: folder_export}
      instagram: {provider: folder_export}

channel_rules: {}
default_channel: midnight-curiosity
```

Remove the old `platforms:` top-level list (now per-channel).

- [ ] **Step 2: Find `runner.py`'s post-creation call site (already located in chunk 8's Task 2)**

Run: `grep -n "insert_post\|style_rules" claudeshorts/generate/runner.py`

- [ ] **Step 3: Wire channel selection into `runner.py`**

Immediately after chunk 8's `layout = style_rules.select_layout(...)` line,
add:

```python
    from ..store import channels as channels_store
    from ..publish import channel_rules

    channel_slug = channel_rules.select_channel(
        item, cfg.get("channel_rules", {}), cfg.get("default_channel", "midnight-curiosity"),
    )
    channel_row = channels_store.get_by_slug(conn, channel_slug)
```

(`cfg` here is the top-level `settings()` dict, matching how `styles` was
read in chunk 8 — read `channel_rules`/`default_channel` as siblings of
`styles`, both top-level keys per Step 1's config shape.) Pass
`channel_id=channel_row["id"]` into the existing `insert_post(...)` call.

- [ ] **Step 4: Add a startup channel-seeding step**

Since `insert_post` now requires a resolvable `channel_id`, the single
configured channel must exist in the DB before the first post is
generated. Add a small idempotent seeding helper called once from the
CLI's startup path (wherever `init_db()` is already called — locate via
`grep -n "init_db()" claudeshorts/cli.py`):

```python
def seed_channels_from_config(conn) -> None:
    from ..config import settings
    from ..store import channels as channels_store
    for entry in settings().get("channels", []):
        if channels_store.get_by_slug(conn, entry["slug"]) is None:
            channels_store.insert_channel(
                conn, slug=entry["slug"], name=entry["name"],
                handle=entry.get("handle"), logo=entry.get("logo"),
                enabled=entry.get("enabled", True),
            )
```

Place this function in `claudeshorts/store/channels.py` (append to the
file from Task 1) and call it right after `init_db()` in the CLI startup
path.

- [ ] **Step 5: Update `render/bridge.py`'s `build_spec`**

Replace the line `channel = dict(cfg.get("channel", {}))` with a lookup
against the post's own `channel_id`:

```python
    from ..store import channels as channels_store, connect
    with connect() as conn:
        channel_row = channels_store.get_channel(conn, post.get("channel_id")) or {}
    channel = {"name": channel_row.get("name", ""), "handle": channel_row.get("handle", ""),
               "logo": channel_row.get("logo")}
```

- [ ] **Step 6: Rewrite `publish/exporter.py::export_post`**

```python
def export_post(post: dict[str, Any], platforms: list[str] | None = None) -> list[Path]:
    config.ensure_dirs()
    with connect() as conn:
        channel = channels_store.get_channel(conn, post["channel_id"])
    cfg = config.settings()
    channel_cfg = next(
        (c for c in cfg.get("channels", []) if c["slug"] == channel["slug"]), {},
    )
    platform_cfgs = channel_cfg.get("platforms", {})
    platforms = platforms or list(platform_cfgs.keys())

    out_dirs: list[Path] = []
    for platform in platforms:
        platform_cfg = platform_cfgs.get(platform, {"provider": "folder_export"})
        provider = registry.get_provider(
            platform_cfg.get("provider", "folder_export"),
            credentials_env=platform_cfg.get("credentials_env"),
        )
        result = provider.publish(post, platform, channel)
        out_dirs.append(Path(result["location"]))

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as conn:
        set_status(conn, post["id"], "exported", published_at=stamp)
        conn.commit()
    return out_dirs
```

Add the corresponding imports (`from .providers import registry`, `from
..store import channels as channels_store`) at the top of the file;
remove the now-unused `_locate_video`/`_locate_slides` helpers (moved into
`FolderExportProvider` in Task 3) and the `shutil`/`PLATFORM_CAPTION`
imports they required, if nothing else in the file still uses them.

- [ ] **Step 7: Run the full test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add config/settings.yaml claudeshorts/generate/runner.py claudeshorts/render/bridge.py claudeshorts/publish/exporter.py claudeshorts/store/channels.py claudeshorts/cli.py
git commit -m "feat: wire multi-channel routing through generation, rendering, and export"
```

---

### Task 6: Data migration for existing posts (SQLite path)

**Files:**
- Create: `scripts/migrate_channel_id.py` (one-off, mirrors chunk 1's migration script style)

- [ ] **Step 1: Write the migration script**

```python
"""One-off: seed the configured channel(s) and backfill posts.channel_id
for every existing row, so no pre-chunk-10 post is left with a null
channel. Safe to re-run (idempotent)."""

from __future__ import annotations

from claudeshorts.config import settings
from claudeshorts.store import channels as channels_store, connect


def main() -> None:
    with connect() as conn:
        for entry in settings().get("channels", []):
            if channels_store.get_by_slug(conn, entry["slug"]) is None:
                channels_store.insert_channel(
                    conn, slug=entry["slug"], name=entry["name"],
                    handle=entry.get("handle"), logo=entry.get("logo"),
                    enabled=entry.get("enabled", True),
                )
        default_slug = settings().get("default_channel")
        default_row = channels_store.get_by_slug(conn, default_slug)
        conn.execute(
            "UPDATE posts SET channel_id = ? WHERE channel_id IS NULL",
            (default_row["id"],),
        )
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM posts WHERE channel_id = ?", (default_row["id"],)).fetchone()[0]
        print(f"backfilled channel_id={default_row['id']} on {n} posts")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against the real `data/app.db`**

Run: `python scripts/migrate_channel_id.py`
Expected output: `backfilled channel_id=1 on <N> posts` where N matches the
post count noted in earlier checkpoints (13, per the session's earlier
DB inspection — confirm it matches before proceeding).

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_channel_id.py
git commit -m "feat: add one-off channel_id backfill migration script"
```

---

### Task 7: Update checkpoint and task tracking

**Files:**
- Modify: `CHECKPOINT_LAST.md`, `TASK_QUEUE.md`

- [ ] **Step 1: Record completion, flag the remaining human-required step**

Update `TASK_QUEUE.md` to move chunk 10 to Done. Update
`CHECKPOINT_LAST.md` noting: the plugin interface and multi-channel model
are fully implemented and tested; the three `*_api.py` providers remain
`NotImplementedError` stubs pending the user obtaining real
YouTube/TikTok/Instagram developer-app credentials — that wiring is
explicitly out of scope until the user provides them (matches this
chunk's "human-required, deferred" status). Next action: chunk 11
(browser-automation profile system + Playwright analytics scraping).

- [ ] **Step 2: Commit**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 10 complete — publishing plugin interface + multi-channel model live, API credentials still pending"
```

---

## Self-Review Notes

**Spec coverage:** `PublishProvider` Protocol + `FolderExportProvider`
(Task 3) match the spec's channel-scoped path requirement
(`publish/<channel_slug>/<platform>/<date>/post_<id>/`). Three API stub
providers (Task 4) match the spec's "real interface, credentials-gated,
no network code yet" requirement. `channel_rules.select_channel` (Task 2)
matches the spec's first-match-in-insertion-order determinism, identical
in shape to chunk 8's `select_layout`. The `channels` table + `posts
.channel_id` + seeding + backfill migration (Tasks 1, 5 Step 4, 6) match
the spec's "full multi-channel model now" decision. Out-of-scope items
(per-channel ingestion routing, real API network calls, channel
management UI) are not addressed by any task, matching the spec.

**Placeholder scan:** Task 1 Step 2 includes a test named
`test_get_by_slug` containing only `pass` — flagged explicitly in the
step's own text as a stub to delete before running, immediately followed
by its real replacement `test_get_by_slug_real`, so an implementer cannot
mistake it for a deliverable. No other steps contain TBD/placeholder
content.

**Type consistency:** `PublishProvider.publish(post, platform, channel)`'s
three-argument shape is identical across `FolderExportProvider` (Task 3)
and all three API stubs (Task 4). `channel` dicts passed into `.publish()`
have a consistent `{"slug": ...}` minimum shape used by both Task 3's and
Task 4's tests. `select_channel`/`select_layout`'s signatures
(`item, rules_dict, default`) are deliberately parallel across chunks 8
and 10 for consistency, not by accident. `registry.get_provider(name, *,
credentials_env=None)`'s keyword-only `credentials_env` matches its use at
both the registry's own tests (Task 4) and `exporter.py`'s call site
(Task 5 Step 6).
