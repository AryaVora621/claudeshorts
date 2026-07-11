# Multi-Profile Data Model (Reshape Sub-Project A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Resume note:** each task below is independently checkpointable — after
> finishing a task, update `TASK_QUEUE.md`'s In-Progress section and
> `CHECKPOINT_LAST.md` with which tasks are done/remaining before stopping,
> per this repo's standing convention. A fresh session (or subagent) can pick
> up any not-yet-started task in a ready wave without re-reading the others.
>
> **Parallel-execution note:** tasks are grouped into **waves**. All tasks in
> a wave have no dependency on each other and can be dispatched to separate
> subagents concurrently; a wave cannot start until every task in the
> previous wave is committed. See "Wave plan" below.

**Goal:** Model fork.ai, Midnight Curiosity, and future brands as distinct
`profiles` in the data model, so ingestion, content memory, generation, and
scheduling can all run independently per profile from one instance.

**Architecture:** A new `profiles` Postgres table holds operational fields
(`slug`, `display_name`, `active`, `auto_publish`, `posts_per_day`,
`platforms`); a `profile_id` FK is added to `items`/`posts`/`threads`/`runs`/
`schedules`. Content identity (generation prompt, source list, brand theme,
browser-session metadata) moves into versioned files under
`config/profiles/<slug>/`, merging in the browser-automation login-profile
concept that already lives at that path. `auto_publish` is the mechanism
that makes a profile "headless" — a rendered post exports immediately
instead of waiting in the review queue.

**Tech Stack:** Python 3.11+, psycopg3, PyYAML, pytest, real Postgres
(Supabase or local docker) for tests — same stack as the rest of the repo.

## Global Constraints

- Python 3.11+, type hints everywhere, PEP 8 (per `CLAUDE.md`).
- No comments explaining *what* code does — only *why*, and only when
  non-obvious.
- Secrets only in `.env`; never duplicate a real secret into a tracked file.
- Schema changes are additive (`CREATE TABLE IF NOT EXISTS` /
  `ADD COLUMN IF NOT EXISTS`), same pattern as the rest of `store/db.py` —
  no separate migration runner exists in this repo.
- `items.content_hash`'s dedupe key becomes `(profile_id, content_hash)` —
  two profiles covering the same story independently is expected, not a bug.
- Full spec: `docs/superpowers/specs/2026-07-11-multi-profile-platform-reshape-design.md`.
- Out of scope for this plan (see spec): analytics collection, dashboard UI
  changes, TikTok/Instagram publish automation. Don't implement those here.

---

## File Structure

- Modify: `claudeshorts/store/db.py` — add `profiles` table + `profile_id`
  columns to the `SCHEMA` string; change `items`'s unique index to composite.
- Create: `claudeshorts/store/profiles.py` — CRUD for the `profiles` table.
- Modify: `claudeshorts/browser/profiles.py` — read from
  `config/profiles/<slug>/profile.yaml` instead of a flat
  `config/profiles/<slug>.yaml`; add `load_sources(slug)` and
  `load_prompt(slug)`.
- Create: `config/profiles/fork-ai/profile.yaml`,
  `config/profiles/fork-ai/sources.yaml` (moved from `config/sources.yaml`),
  `config/profiles/fork-ai/prompt.md`.
- Create: `config/profiles/midnight-curiosity/profile.yaml`,
  `config/profiles/midnight-curiosity/sources.yaml`,
  `config/profiles/midnight-curiosity/prompt.md`.
- Modify: `claudeshorts/store/items.py`, `store/posts.py`, `store/threads.py`,
  `store/runs.py` — add `profile_id` to insert/query functions.
- Modify: `claudeshorts/ingest/runner.py`, `claudeshorts/generate/select.py`,
  `claudeshorts/generate/runner.py` — pass `profile_id` through to the store
  layer (mechanical plumbing, Task 4); then load per-profile
  `sources.yaml`/`prompt.md` instead of the global config (behavioral,
  Task 6).
- Modify: `claudeshorts/services/pipeline_service.py`,
  `claudeshorts/services/posts_service.py` — accept/thread `profile_id`;
  `posts_service` gains the `auto_publish` short-circuit.
- Modify: `claudeshorts/scheduling/scheduler.py` — seed one schedule set per
  active profile instead of one global set.
- Create: `scripts/migrate_profiles_backfill.py` — one-time backfill script.
- Modify/create test files mirroring each of the above under `tests/`.

## Wave plan

- **Wave 1** (start immediately, no dependencies): Task 1, Task 3
- **Wave 2** (after Wave 1 commits): Task 2, Task 4
- **Wave 3** (after Wave 2 commits): Task 5, Task 6, Task 7
- **Wave 4** (after Wave 3 commits): Task 8

---

### Task 1: Schema — `profiles` table + `profile_id` columns

**Wave:** 1 (no dependencies — start immediately)

**Files:**
- Modify: `claudeshorts/store/db.py`
- Test: `tests/store/test_db_schema.py` (new)

**Interfaces:**
- Produces: a `profiles` table and `profile_id BIGINT REFERENCES profiles(id)`
  columns on `items`, `posts`, `threads`, `runs`, `schedules`. Later tasks
  depend on these columns existing.

- [ ] **Step 1: Write the failing test**

```python
# tests/store/test_db_schema.py
from __future__ import annotations

from claudeshorts.store import connect, init_db


def test_profiles_table_and_profile_id_columns_exist():
    init_db()
    with connect() as conn:
        cols = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE column_name = 'profile_id' AND table_name IN "
            "('items', 'posts', 'threads', 'runs', 'schedules')"
        ).fetchall()
        tables_with_profile_id = {r["table_name"] for r in cols}
        assert tables_with_profile_id == {
            "items", "posts", "threads", "runs", "schedules",
        }

        profiles_cols = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'profiles'"
        ).fetchall()
        assert {r["column_name"] for r in profiles_cols} == {
            "id", "slug", "display_name", "active", "auto_publish",
            "posts_per_day", "platforms", "created_at",
        }


def test_items_content_hash_unique_index_is_composite_with_profile_id():
    init_db()
    with connect() as conn:
        idx = conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'idx_items_content_hash'"
        ).fetchone()
        assert idx is not None
        assert "profile_id" in idx["indexdef"]
        assert "content_hash" in idx["indexdef"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_db_schema.py -v`
Expected: FAIL — `profiles` table doesn't exist yet, and the old
`idx_items_content_hash` index has no `profile_id` in its definition.

- [ ] **Step 3: Update the schema**

In `claudeshorts/store/db.py`, replace the `items` table's unique index line:

```python
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_content_hash ON items(content_hash);
```

with:

```python
DROP INDEX IF EXISTS idx_items_content_hash;
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_content_hash
    ON items(profile_id, content_hash);
```

Add a `profiles` table and the `profile_id` columns near the top of the
`SCHEMA` string, before the `items` table definition (so the FK target
exists first):

```python
CREATE TABLE IF NOT EXISTS profiles (
    id            BIGSERIAL PRIMARY KEY,
    slug          TEXT        NOT NULL UNIQUE,
    display_name  TEXT        NOT NULL,
    active        BOOLEAN     NOT NULL DEFAULT true,
    auto_publish  BOOLEAN     NOT NULL DEFAULT false,
    posts_per_day INTEGER     NOT NULL DEFAULT 3,
    platforms     JSONB       NOT NULL DEFAULT '["youtube","tiktok","instagram"]'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Then, after the existing `CREATE TABLE` statements for `items`, `posts`,
`threads`, `runs`, and `schedules` (each already exists in the file), add
this block at the end of `SCHEMA` (alongside the other `ALTER TABLE ...
ADD COLUMN IF NOT EXISTS` upgrade statements already there):

```python
-- Multi-profile reshape: scope items/posts/threads/runs/schedules to a
-- profile. NULL profile_id on legacy rows is resolved by
-- scripts/migrate_profiles_backfill.py (Task 5), not by this schema.
ALTER TABLE items     ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE posts     ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE threads   ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE runs      ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE schedules ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);

CREATE INDEX IF NOT EXISTS idx_posts_profile_status ON posts(profile_id, status);
CREATE INDEX IF NOT EXISTS idx_runs_profile_date ON runs(profile_id, run_date);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_db_schema.py -v`
Expected: PASS

- [ ] **Step 5: Run the full store test suite to check for regressions**

Run: `pytest tests/store/ -v`
Expected: PASS (existing tests don't reference `profile_id`, so the new
nullable columns shouldn't break them — the old `idx_items_content_hash`
tests, if any assert on the index name/columns directly, will need review;
fix any that assumed a single-column index).

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/store/db.py tests/store/test_db_schema.py
git commit -m "feat: add profiles table and profile_id columns to items/posts/threads/runs/schedules"
```

---

### Task 2: `store/profiles.py` — CRUD for the `profiles` table

**Wave:** 2 (depends on Task 1)

**Files:**
- Create: `claudeshorts/store/profiles.py`
- Modify: `claudeshorts/store/__init__.py` (export the new module's public
  functions, matching how `store/__init__.py` already re-exports from
  `items.py`/`posts.py`/etc. — check the existing file for the pattern
  before editing)
- Test: `tests/store/test_profiles.py` (new)

**Interfaces:**
- Produces:
  - `upsert_profile(conn, *, slug: str, display_name: str, posts_per_day: int = 3, platforms: list[str] | None = None) -> int`
  - `get_profile(conn, slug: str) -> dict[str, Any] | None`
  - `get_profile_by_id(conn, profile_id: int) -> dict[str, Any] | None`
  - `list_profiles(conn, *, active_only: bool = False) -> list[dict[str, Any]]`
  - `set_auto_publish(conn, profile_id: int, auto_publish: bool) -> None`
- Consumes: nothing beyond `psycopg.Connection` and the `profiles` table
  from Task 1.

- [ ] **Step 1: Write the failing tests**

```python
# tests/store/test_profiles.py
from __future__ import annotations

from claudeshorts.store import connect
from claudeshorts.store.profiles import (
    get_profile,
    get_profile_by_id,
    list_profiles,
    set_auto_publish,
    upsert_profile,
)


def test_upsert_profile_creates_then_updates_without_touching_auto_publish():
    with connect() as conn:
        pid = upsert_profile(
            conn, slug="fork-ai", display_name="fork.ai",
            posts_per_day=3, platforms=["youtube", "tiktok", "instagram"],
        )
        set_auto_publish(conn, pid, True)

        # Re-seeding (e.g. app boot re-reading profile.yaml) must not
        # clobber the operator-toggled auto_publish flag.
        pid2 = upsert_profile(
            conn, slug="fork-ai", display_name="fork.ai (renamed)",
            posts_per_day=5, platforms=["youtube"],
        )
        assert pid2 == pid

        row = get_profile(conn, "fork-ai")
        assert row["display_name"] == "fork.ai (renamed)"
        assert row["posts_per_day"] == 5
        assert row["platforms"] == ["youtube"]
        assert row["auto_publish"] is True  # untouched by the reseed


def test_get_profile_by_id_and_missing_returns_none():
    with connect() as conn:
        pid = upsert_profile(conn, slug="mc", display_name="Midnight Curiosity")
        assert get_profile_by_id(conn, pid)["slug"] == "mc"
        assert get_profile_by_id(conn, 999999) is None
        assert get_profile(conn, "no-such-slug") is None


def test_list_profiles_active_only_filter():
    with connect() as conn:
        a = upsert_profile(conn, slug="active-one", display_name="Active One")
        b = upsert_profile(conn, slug="inactive-one", display_name="Inactive One")
        conn.execute("UPDATE profiles SET active = false WHERE id = %s", (b,))

        all_slugs = {p["slug"] for p in list_profiles(conn)}
        active_slugs = {p["slug"] for p in list_profiles(conn, active_only=True)}
        assert {"active-one", "inactive-one"} <= all_slugs
        assert "active-one" in active_slugs
        assert "inactive-one" not in active_slugs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/store/test_profiles.py -v`
Expected: FAIL — `claudeshorts.store.profiles` doesn't exist yet.

- [ ] **Step 3: Implement `claudeshorts/store/profiles.py`**

```python
"""Data-access helpers for the `profiles` table (multi-brand content profiles,
e.g. fork.ai, Midnight Curiosity).

`upsert_profile` is safe to call on every boot (re-seeding from
`config/profiles/<slug>/profile.yaml`) because the ON CONFLICT arm never
touches `auto_publish` or `active` — those are operator-toggled at runtime,
mirroring how `scheduling/store.py::upsert_schedule` protects `next_run_at`.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb


def upsert_profile(
    conn: psycopg.Connection, *, slug: str, display_name: str,
    posts_per_day: int = 3, platforms: list[str] | None = None,
) -> int:
    row = conn.execute(
        "INSERT INTO profiles (slug, display_name, posts_per_day, platforms) "
        "VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (slug) DO UPDATE SET "
        "display_name = EXCLUDED.display_name, "
        "posts_per_day = EXCLUDED.posts_per_day, "
        "platforms = EXCLUDED.platforms "
        "RETURNING id",
        (slug, display_name, posts_per_day, Jsonb(platforms or ["youtube", "tiktok", "instagram"])),
    ).fetchone()
    return int(row["id"])


def get_profile(conn: psycopg.Connection, slug: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM profiles WHERE slug = %s", (slug,)).fetchone()
    return dict(row) if row else None


def get_profile_by_id(conn: psycopg.Connection, profile_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM profiles WHERE id = %s", (profile_id,)).fetchone()
    return dict(row) if row else None


def list_profiles(conn: psycopg.Connection, *, active_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM profiles"
    if active_only:
        sql += " WHERE active = true"
    sql += " ORDER BY id ASC"
    return [dict(r) for r in conn.execute(sql).fetchall()]


def set_auto_publish(conn: psycopg.Connection, profile_id: int, auto_publish: bool) -> None:
    conn.execute(
        "UPDATE profiles SET auto_publish = %s WHERE id = %s",
        (auto_publish, profile_id),
    )
```

- [ ] **Step 4: Export from `claudeshorts/store/__init__.py`**

Open `claudeshorts/store/__init__.py`, find the existing per-module import/
export block (it re-exports functions from `items.py`, `posts.py`, etc. —
match that exact pattern), and add:

```python
from .profiles import (
    get_profile,
    get_profile_by_id,
    list_profiles,
    set_auto_publish,
    upsert_profile,
)
```

Add the same names to `__all__` if the file defines one (check first).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/store/test_profiles.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/store/profiles.py claudeshorts/store/__init__.py tests/store/test_profiles.py
git commit -m "feat: add store/profiles.py CRUD for the profiles table"
```

---

### Task 3: Restructure `config/profiles/<slug>/`, merge into `browser/profiles.py`

**Wave:** 1 (no dependencies — start immediately, in parallel with Task 1)

**Files:**
- Modify: `claudeshorts/browser/profiles.py`
- Modify: `tests/browser/test_profiles.py`
- Create: `config/profiles/fork-ai/profile.yaml`
- Create: `config/profiles/fork-ai/sources.yaml` (content = current
  `config/sources.yaml`, moved not copied — delete the old top-level file
  in this task once the move is verified)
- Create: `config/profiles/fork-ai/prompt.md`
- Create: `config/profiles/midnight-curiosity/profile.yaml`
- Create: `config/profiles/midnight-curiosity/sources.yaml`
- Create: `config/profiles/midnight-curiosity/prompt.md`

**Interfaces:**
- Produces:
  - `load_profile(slug: str) -> dict` (existing signature kept, new file
    location)
  - `list_profiles() -> list[dict]` (existing signature kept, new file
    location — note this is a **different, filesystem-only** `list_profiles`
    from Task 2's DB-backed `store.profiles.list_profiles`; the profiles API
    route and dashboard will need to be clear about which one they mean when
    sub-project C touches them — not this plan's concern, just flagging the
    name collision so nobody is surprised)
  - `load_sources(slug: str) -> list[dict]` (new)
  - `load_prompt(slug: str) -> str` (new)
  - `storage_state_path(slug: str) -> Path` (existing signature, unchanged
    behavior — session state still lives under top-level `profiles/<slug>/`,
    separate from `config/profiles/<slug>/`, per the existing file's own
    docstring about keeping versionable metadata separate from gitignored
    session state)

- [ ] **Step 1: Write the failing tests**

Replace the contents of `tests/browser/test_profiles.py` with (the existing
file's tests for `storage_state_path` and the missing-file error case are
preserved below; only the profile-loading tests change shape to match the
new nested layout — read the existing file first to confirm you're not
dropping a case):

```python
# tests/browser/test_profiles.py
from __future__ import annotations

import pytest

from claudeshorts.browser.profiles import (
    load_profile,
    load_prompt,
    load_sources,
    list_profiles,
    storage_state_path,
)


@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    d = tmp_path / "profiles"
    d.mkdir()
    monkeypatch.setattr("claudeshorts.browser.profiles.PROFILES_DIR", d)
    return d


def _write_profile(profiles_dir, slug: str, profile_yaml: str, sources_yaml: str = "sources: []\n", prompt_md: str = "Be concise.\n"):
    d = profiles_dir / slug
    d.mkdir()
    (d / "profile.yaml").write_text(profile_yaml)
    (d / "sources.yaml").write_text(sources_yaml)
    (d / "prompt.md").write_text(prompt_md)


def test_load_profile_reads_nested_yaml(profiles_dir):
    _write_profile(profiles_dir, "fork-ai", "display_name: fork.ai\nbrowser: chromium\n")
    profile = load_profile("fork-ai")
    assert profile["display_name"] == "fork.ai"
    assert profile["browser"] == "chromium"


def test_load_profile_defaults_login_health_to_unknown(profiles_dir):
    _write_profile(profiles_dir, "fork-ai", "display_name: fork.ai\n")
    assert load_profile("fork-ai")["login_health"] == "unknown"


def test_load_profile_missing_raises_file_not_found(profiles_dir):
    with pytest.raises(FileNotFoundError):
        load_profile("no-such-profile")


def test_list_profiles_returns_all(profiles_dir):
    _write_profile(profiles_dir, "fork-ai", "display_name: fork.ai\n")
    _write_profile(profiles_dir, "midnight-curiosity", "display_name: Midnight Curiosity\n")
    slugs = {p["slug"] for p in list_profiles()}
    assert slugs == {"fork-ai", "midnight-curiosity"}


def test_list_profiles_empty_dir_returns_empty_list(profiles_dir):
    assert list_profiles() == []


def test_load_sources_reads_per_profile_sources_yaml(profiles_dir):
    _write_profile(
        profiles_dir, "fork-ai", "display_name: fork.ai\n",
        sources_yaml="sources:\n  - name: hn\n    kind: hackernews\n",
    )
    sources = load_sources("fork-ai")
    assert sources == [{"name": "hn", "kind": "hackernews"}]


def test_load_prompt_reads_per_profile_prompt_md(profiles_dir):
    _write_profile(profiles_dir, "fork-ai", "display_name: fork.ai\n", prompt_md="Be concise.\n")
    assert load_prompt("fork-ai") == "Be concise.\n"


def test_storage_state_path_under_state_dir(profiles_dir):
    # unchanged behavior: session state stays under the top-level, gitignored
    # `profiles/` dir, independent of config_profiles restructuring
    from claudeshorts.browser.profiles import STATE_DIR
    assert storage_state_path("fork-ai") == STATE_DIR / "fork-ai" / "storage_state.json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/browser/test_profiles.py -v`
Expected: FAIL — `load_profile("fork-ai")` still looks for
`config/profiles/fork-ai.yaml` (a flat file), and `load_sources`/
`load_prompt` don't exist yet.

- [ ] **Step 3: Rewrite `claudeshorts/browser/profiles.py`**

```python
"""Per-profile config: browser-automation session metadata, RSS/HN/Reddit
sources, and the generation prompt all live together under
`config/profiles/<slug>/` since a content profile inherently owns its own
browser session (for scraping/publishing) alongside its content identity.

Session STATE (real cookies) stays separate, under the gitignored top-level
`profiles/<slug>/` — never mix it with this directory, which is safe to
review in a PR.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PROFILES_DIR = Path("config/profiles")
STATE_DIR = Path("profiles")

_DEFAULTS = {"login_health": "unknown", "browser": "chromium", "notes": ""}


def _profile_dir(slug: str) -> Path:
    return PROFILES_DIR / slug


def load_profile(slug: str) -> dict:
    path = _profile_dir(slug) / "profile.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no profile config at {path}")
    data = yaml.safe_load(path.read_text()) or {}
    return {**_DEFAULTS, **data}


def list_profiles() -> list[dict]:
    if not PROFILES_DIR.is_dir():
        return []
    slugs = sorted(p.parent.name for p in PROFILES_DIR.glob("*/profile.yaml"))
    return [{"slug": slug, **load_profile(slug)} for slug in slugs]


def load_sources(slug: str) -> list[dict]:
    path = _profile_dir(slug) / "sources.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no sources config at {path}")
    return (yaml.safe_load(path.read_text()) or {}).get("sources", [])


def load_prompt(slug: str) -> str:
    path = _profile_dir(slug) / "prompt.md"
    if not path.exists():
        raise FileNotFoundError(f"no prompt file at {path}")
    return path.read_text()


def storage_state_path(slug: str) -> Path:
    return STATE_DIR / slug / "storage_state.json"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/browser/test_profiles.py -v`
Expected: PASS

- [ ] **Step 5: Create the two real profile directories**

```bash
mkdir -p config/profiles/fork-ai config/profiles/midnight-curiosity
git mv config/sources.yaml config/profiles/fork-ai/sources.yaml
```

Create `config/profiles/fork-ai/profile.yaml`:

```yaml
display_name: "fork.ai"
handle: "@fork.ai"
brand_color: "#A855F7"
posts_per_day: 3
platforms: ["youtube", "tiktok", "instagram"]
browser: chromium
login_health: unknown
notes: ""
```

Create `config/profiles/fork-ai/prompt.md` — move the existing generation
system prompt text out of wherever it's currently inlined (check
`claudeshorts/generate/generator.py` for `build_cli_prompt`/
`build_user_prompt` — this task only relocates the *profile-specific tone*
portion, not the structural JSON-schema instructions, which stay in
`generator.py` since they're not profile-specific; read that file before
writing this content so the split is accurate):

```markdown
Voice: concise, technical, no hype, no exclamation points. Assume the
reader follows tech/AI news daily and wants the signal without the
marketing language. Never use em dashes.
```

Create `config/profiles/midnight-curiosity/profile.yaml`:

```yaml
display_name: "Midnight Curiosity"
handle: "@midnight.curiosity"
brand_color: "#6D28D9"
posts_per_day: 3
platforms: ["youtube", "tiktok", "instagram"]
browser: chromium
login_health: unknown
notes: "New profile — SAT/study niche, not yet publishing live content."
```

Create `config/profiles/midnight-curiosity/sources.yaml` (placeholder shape,
real feed URLs are a follow-up task outside this plan's scope — see spec's
"explicitly out of scope" list, this plan only builds the mechanism):

```yaml
sources: []
```

Create `config/profiles/midnight-curiosity/prompt.md`:

```markdown
Voice: calm, encouraging, precise. Written for a student studying SAT
material — clear explanations, no filler, no hype. Never use em dashes.
```

- [ ] **Step 6: Update `claudeshorts/config.py` — remove the now-unused global `sources()`**

`config.py`'s `sources()` function and `SOURCES_PATH` constant read the old
top-level `config/sources.yaml`, which Step 5 just moved. Grep for every
caller of `claudeshorts.config.sources` before removing it:

```bash
grep -rn "config.sources\|from .config import sources\|from ..config import sources" claudeshorts/ tests/
```

Each hit is a caller that still needs *a* source list until Task 6 makes it
profile-aware — leave `config.py::sources()` in place for this task (don't
delete it yet, its callers aren't updated until Task 6) but point it at
`config/profiles/fork-ai/sources.yaml` as a temporary default so nothing
breaks between this task and Task 6:

```python
# claudeshorts/config.py — change SOURCES_PATH to:
SOURCES_PATH = CONFIG_DIR / "profiles" / "fork-ai" / "sources.yaml"
```

- [ ] **Step 7: Run the full test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: PASS (this is a real Postgres-backed suite and takes 5-10+
minutes — let it finish, don't assume a hang; see
`docs/ARCHITECTURE.md`'s Testing section)

- [ ] **Step 8: Commit**

```bash
git add claudeshorts/browser/profiles.py claudeshorts/config.py tests/browser/test_profiles.py config/profiles/
git commit -m "feat: restructure config/profiles/<slug>/ to hold session, sources, and prompt together; seed fork-ai and midnight-curiosity"
```

---

### Task 4: Thread `profile_id` through `items`/`posts`/`threads`/`runs`

**Wave:** 2 (depends on Task 1)

**Files:**
- Modify: `claudeshorts/store/items.py`
- Modify: `claudeshorts/store/posts.py`
- Modify: `claudeshorts/store/threads.py`
- Modify: `claudeshorts/store/runs.py`
- Modify: `claudeshorts/ingest/runner.py` (adds a `profile_id` parameter,
  passes it to `insert_item`)
- Test: `tests/store/test_items.py`, `test_posts.py`, `test_threads.py`,
  `test_runs.py` (extend existing files — read them first, add new cases
  rather than rewriting what already passes)

**Interfaces:**
- Produces (signature changes — every caller across the codebase that hits
  these functions needs a `profile_id`; Task 6 handles the service-layer
  callers, this task handles the store layer and its most direct caller,
  `ingest/runner.py`):
  - `insert_item(conn, item: dict, profile_id: int) -> bool`
  - `recent_items(conn, days: int, profile_id: int) -> list[dict]`
  - `count_items(conn, profile_id: int | None = None) -> int` (kept
    optional — total-across-all-profiles is still a meaningful number for
    a future cross-profile dashboard tile)
  - `insert_post(conn, ..., profile_id: int) -> int` (add to the existing
    keyword args — check current signature in `store/posts.py` before
    editing, don't drop any existing parameter)
  - `used_item_ids(conn, days: int, profile_id: int) -> set[int]`
  - `upsert_thread(conn, *, slug: str, title: str, summary: str | None, profile_id: int) -> int`
  - `open_threads(conn, profile_id: int) -> list[dict]`
  - `start_run(conn, run_date: str, profile_id: int) -> int`
  - `latest_run_for_date(conn, run_date: str, profile_id: int) -> dict | None`
  - `run_ingest(profile_id: int, since: str | None = None, limit: int | None = None) -> dict`
- Consumes: `store.profiles.get_profile_by_id` (Task 2) is NOT required by
  this task — it only threads an already-known `profile_id` through; slug
  resolution happens in Task 6.

- [ ] **Step 1: Write the failing tests**

Add these cases to the existing test files (append, don't replace — the
existing tests for e.g. `insert_item` without profile scoping will need
their calls updated to pass a `profile_id`, since the function signature is
changing; update those call sites in the same edit rather than leaving them
broken):

```python
# tests/store/test_items.py — add
def test_insert_item_scopes_dedupe_by_profile(db_conn):
    item = {
        "source": "hn", "url": "https://example.com/a", "title": "A",
        "summary": "s", "published_at": None, "content_hash": "hash-a",
    }
    assert insert_item(db_conn, item, profile_id=1) is True
    # Same content_hash, different profile: NOT a duplicate.
    assert insert_item(db_conn, item, profile_id=2) is True
    # Same content_hash, same profile: IS a duplicate.
    assert insert_item(db_conn, item, profile_id=1) is False


def test_recent_items_scoped_to_profile(db_conn):
    insert_item(db_conn, {**BASE_ITEM, "content_hash": "h1"}, profile_id=1)
    insert_item(db_conn, {**BASE_ITEM, "content_hash": "h2"}, profile_id=2)
    profile_1_items = recent_items(db_conn, days=7, profile_id=1)
    assert {i["content_hash"] for i in profile_1_items} == {"h1"}
```

```python
# tests/store/test_posts.py — add
def test_insert_post_persists_profile_id(db_conn):
    post_id = insert_post(db_conn, item_ids=[1], title="T", slides=[], profile_id=1)
    assert get_post(db_conn, post_id)["profile_id"] == 1
```

```python
# tests/store/test_threads.py — add
def test_open_threads_scoped_to_profile(db_conn):
    upsert_thread(db_conn, slug="a", title="A", summary=None, profile_id=1)
    upsert_thread(db_conn, slug="b", title="B", summary=None, profile_id=2)
    assert {t["slug"] for t in open_threads(db_conn, profile_id=1)} == {"a"}
```

```python
# tests/store/test_runs.py — add
def test_latest_run_for_date_scoped_to_profile(db_conn):
    start_run(db_conn, "2026-07-11", profile_id=1)
    assert latest_run_for_date(db_conn, "2026-07-11", profile_id=2) is None
    assert latest_run_for_date(db_conn, "2026-07-11", profile_id=1) is not None
```

Note: the exact fixture name (`db_conn` above) and existing helper constants
(`BASE_ITEM` above) must match what's already in each test file — read each
file first and reuse its existing fixtures rather than inventing new ones.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/store/test_items.py tests/store/test_posts.py tests/store/test_threads.py tests/store/test_runs.py -v`
Expected: FAIL — `TypeError: insert_item() got an unexpected keyword argument 'profile_id'` (or similar) for each.

- [ ] **Step 3: Add `profile_id` to `store/items.py`**

Update `insert_item`, `recent_items`, `count_items`, `get_items` (leave
`get_item`/`latest_items` — dashboard-browsing helpers — unscoped for now,
they're out of this task's caller set and sub-project C will decide their
final shape):

```python
def insert_item(conn: psycopg.Connection, item: dict[str, Any], profile_id: int) -> bool:
    cur = conn.execute(
        "INSERT INTO items "
        "(source, url, title, summary, published_at, content_hash, profile_id) "
        "VALUES (%(source)s, %(url)s, %(title)s, %(summary)s, "
        "%(published_at)s, %(content_hash)s, %(profile_id)s) "
        "ON CONFLICT (profile_id, content_hash) DO NOTHING",
        {**{k: item.get(k) for k in ITEM_FIELDS}, "profile_id": profile_id},
    )
    return cur.rowcount > 0


def recent_items(conn: psycopg.Connection, days: int, profile_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM items WHERE profile_id = %s AND fetched_at >= now() - (%s || ' days')::interval "
        "ORDER BY COALESCE(published_at, fetched_at::text) DESC",
        (profile_id, int(days)),
    ).fetchall()
    return [dict(r) for r in rows]


def count_items(conn: psycopg.Connection, profile_id: int | None = None) -> int:
    if profile_id is None:
        return conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]
    return conn.execute(
        "SELECT COUNT(*) AS n FROM items WHERE profile_id = %s", (profile_id,)
    ).fetchone()["n"]
```

- [ ] **Step 4: Add `profile_id` to `store/posts.py`, `store/threads.py`, `store/runs.py`**

Read each file's current implementation first (shown earlier in this
session — `insert_post`, `used_item_ids`, `upsert_thread`, `open_threads`,
`start_run`, `latest_run_for_date`) and add a required `profile_id`
parameter to each, threading it into the relevant `INSERT`/`WHERE` clause
the same way Step 3 did for `items.py`. For `insert_post`, add `profile_id`
as a new required keyword-only parameter and include it in the `INSERT`
column list. For `upsert_thread`, add `profile_id` to both the `INSERT`
column list and a `WHERE profile_id = %s` clause is NOT needed on the
`ON CONFLICT (slug)` target — but note the `threads.slug` unique constraint
is currently **global**; if two profiles independently open a thread with
the same slug (e.g. both derive `"gpt-6-launch"` from token overlap) they'd
collide. Fix this in the same step: change `threads`'s unique constraint
from `slug` alone to `(profile_id, slug)` — this requires one more schema
edit in `store/db.py` (`ALTER TABLE threads DROP CONSTRAINT IF EXISTS
threads_slug_key; CREATE UNIQUE INDEX IF NOT EXISTS idx_threads_profile_slug
ON threads(profile_id, slug);`) alongside the `ON CONFLICT` clause changing
from `(slug)` to `(profile_id, slug)`.

- [ ] **Step 5: Update `ingest/runner.py`**

```python
def run_ingest(
    profile_id: int, since: str | None = None, limit: int | None = None,
) -> dict[str, Any]:
    ...
    with connect() as conn:
        for i, source in enumerate(all_sources, 1):
            ...
            for item in items:
                ...
                if insert_item(conn, item, profile_id):
                    ...
        conn.commit()
        stats["total_items"] = count_items(conn, profile_id)
    return stats
```

(`all_sources` still comes from the global `load_sources()` at this point —
Task 6 changes that call to `browser.profiles.load_sources(slug)`. This
task only adds the `profile_id` parameter and threads it into the store
calls, so `ingest/runner.py`'s tests need a `profile_id` passed at the call
site but the *source list* used is unchanged until Task 6.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/store/ tests/ingest/ -v`
Expected: PASS

- [ ] **Step 7: Run the full test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: PASS — this will surface every other caller of the now-changed
signatures (dashboard routes, API routes, `generate/runner.py`, etc.) as
failures. **Do not fix those callers in this task** — Task 6 (and, for
`posts_service`, Task 7) own them. Instead, confirm the failures are
exactly "missing profile_id argument" style errors in those specific files
and note them in your task handoff so Wave 3 has an accurate starting
point. If the failure list is short enough to fix trivially (e.g. a
dashboard route that only needs `profile_id=1` hardcoded as a stopgap),
that's acceptable here since it's mechanical, not behavioral — use
judgment, but don't implement Task 6's actual per-profile config loading
early.

- [ ] **Step 8: Commit**

```bash
git add claudeshorts/store/items.py claudeshorts/store/posts.py claudeshorts/store/threads.py claudeshorts/store/runs.py claudeshorts/store/db.py claudeshorts/ingest/runner.py tests/store/ tests/ingest/
git commit -m "feat: thread profile_id through items/posts/threads/runs store layer and ingest runner"
```

---

### Task 5: One-time migration/backfill script

**Wave:** 3 (depends on Task 2, Task 3, Task 4)

**Files:**
- Create: `scripts/migrate_profiles_backfill.py`
- Test: `tests/scripts/test_migrate_profiles_backfill.py` (new)

**Interfaces:**
- Produces: `backfill_profiles(conn) -> dict[str, int]` — returns counts of
  rows updated per table, for the script's printed summary and for the test
  to assert against.
- Consumes: `store.profiles.upsert_profile` (Task 2),
  `config.profiles.load_profile("fork-ai")` (Task 3, note this is
  `claudeshorts.browser.profiles.load_profile`, not a new `config.profiles`
  module — name it accurately when importing).

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_migrate_profiles_backfill.py
from __future__ import annotations

from claudeshorts.store import connect
from scripts.migrate_profiles_backfill import backfill_profiles


def test_backfill_assigns_legacy_rows_to_fork_ai(db_conn):
    # Simulate pre-migration rows: insert directly with profile_id left NULL.
    db_conn.execute(
        "INSERT INTO items (source, url, title, content_hash) "
        "VALUES ('hn', 'https://x', 'X', 'legacy-hash')"
    )
    db_conn.execute(
        "INSERT INTO posts (title, status) VALUES ('Legacy Post', 'draft')"
    )
    db_conn.commit()

    counts = backfill_profiles(db_conn)

    fork_ai_id = db_conn.execute(
        "SELECT id FROM profiles WHERE slug = 'fork-ai'"
    ).fetchone()["id"]
    remaining_null_items = db_conn.execute(
        "SELECT COUNT(*) AS n FROM items WHERE profile_id IS NULL"
    ).fetchone()["n"]
    remaining_null_posts = db_conn.execute(
        "SELECT COUNT(*) AS n FROM posts WHERE profile_id IS NULL"
    ).fetchone()["n"]

    assert remaining_null_items == 0
    assert remaining_null_posts == 0
    assert counts["items"] >= 1
    assert counts["posts"] >= 1

    item_profile = db_conn.execute(
        "SELECT profile_id FROM items WHERE content_hash = 'legacy-hash'"
    ).fetchone()["profile_id"]
    assert item_profile == fork_ai_id


def test_backfill_is_idempotent(db_conn):
    backfill_profiles(db_conn)
    counts_second_run = backfill_profiles(db_conn)
    assert counts_second_run == {
        "items": 0, "posts": 0, "threads": 0, "runs": 0, "schedules": 0,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_migrate_profiles_backfill.py -v`
Expected: FAIL — `scripts.migrate_profiles_backfill` doesn't exist.

- [ ] **Step 3: Implement the script**

```python
# scripts/migrate_profiles_backfill.py
"""One-time backfill: assign every profile_id-less row in items/posts/
threads/runs/schedules to the fork-ai profile.

Safe to re-run (idempotent) — only touches rows where profile_id IS NULL,
so a second run reports zero rows changed everywhere.

Historical content in this repo was all generated under the tech/AI news
identity that fork.ai now represents (Midnight Curiosity was a pre-rebrand
placeholder that was never actually live), so backfilling everything onto
fork-ai is correct, not a guess.
"""

from __future__ import annotations

import psycopg

from claudeshorts.browser.profiles import load_profile
from claudeshorts.store.profiles import upsert_profile

TABLES = ("items", "posts", "threads", "runs", "schedules")


def backfill_profiles(conn: psycopg.Connection) -> dict[str, int]:
    fork_ai_config = load_profile("fork-ai")
    fork_ai_id = upsert_profile(
        conn, slug="fork-ai", display_name=fork_ai_config["display_name"],
        posts_per_day=fork_ai_config.get("posts_per_day", 3),
        platforms=fork_ai_config.get("platforms"),
    )

    mc_config = load_profile("midnight-curiosity")
    upsert_profile(
        conn, slug="midnight-curiosity", display_name=mc_config["display_name"],
        posts_per_day=mc_config.get("posts_per_day", 3),
        platforms=mc_config.get("platforms"),
    )

    counts: dict[str, int] = {}
    for table in TABLES:
        cur = conn.execute(
            f"UPDATE {table} SET profile_id = %s WHERE profile_id IS NULL",
            (fork_ai_id,),
        )
        counts[table] = cur.rowcount
    conn.commit()
    return counts


if __name__ == "__main__":
    from claudeshorts.store import connect

    with connect() as conn:
        result = backfill_profiles(conn)
    print("Backfilled profile_id onto legacy rows:")
    for table, n in result.items():
        print(f"  {table}: {n}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scripts/test_migrate_profiles_backfill.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_profiles_backfill.py tests/scripts/test_migrate_profiles_backfill.py
git commit -m "feat: add one-time backfill script assigning legacy rows to the fork-ai profile"
```

---

### Task 6: Profile-scope `ingest`/`select`/`generate` services

**Wave:** 3 (depends on Task 2, Task 3, Task 4)

**Files:**
- Modify: `claudeshorts/generate/select.py`
- Modify: `claudeshorts/generate/runner.py`
- Modify: `claudeshorts/services/pipeline_service.py`
- Modify: `claudeshorts/jobs/registry.py` (job payloads gain `profile_id`)
- Test: extend `tests/generate/test_select.py` (if it exists — check first;
  create it if not), `tests/generate/test_runner.py`,
  `tests/services/test_pipeline_service.py`, `tests/jobs/test_registry.py`

**Interfaces:**
- Produces:
  - `select_topics(profile_id: int, limit: int | None = None, lookback_days: int | None = None) -> list[dict]`
  - `run_generate(profile_id: int, limit: int | None = None, on_progress=None) -> list[dict]`
  - `run_ingest_service(profile_id: int, since=None, limit=None) -> dict`
  - `run_generate_service(profile_id: int, limit=None, on_progress=None) -> list[dict]`
- Consumes: `browser.profiles.load_sources(slug)`, `load_prompt(slug)`
  (Task 3); `store.profiles.get_profile_by_id` (Task 2, to resolve
  `profile_id` → `slug` where a slug is needed for the file-based config
  lookups); `select_topics`/`run_ingest` (Task 4's new signatures).

- [ ] **Step 1: Write the failing tests**

```python
# tests/generate/test_select.py — add or create
def test_select_topics_uses_profile_specific_sources(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "claudeshorts.generate.select.load_sources",
        lambda slug: calls.append(slug) or [{"name": "hn", "weight": 1.0}],
    )
    # ... set up a profile row + items scoped to it, call select_topics(profile_id=<id>) ...
    # assert calls == ["fork-ai"]  (or whichever slug the test profile has)
```

```python
# tests/services/test_pipeline_service.py — add
def test_run_ingest_service_requires_profile_id(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "claudeshorts.services.pipeline_service.run_ingest",
        lambda profile_id, since=None, limit=None: captured.update(profile_id=profile_id) or {},
    )
    run_ingest_service(profile_id=42)
    assert captured["profile_id"] == 42
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/generate/test_select.py tests/services/test_pipeline_service.py -v`
Expected: FAIL — current signatures don't accept/require `profile_id`.

- [ ] **Step 3: Update `generate/select.py`**

Replace the module-level `_source_weights()` (which currently calls the
global `load_sources()`) and `select_topics`'s signature:

```python
from ..browser.profiles import load_prompt, load_sources as load_profile_sources
from ..store.profiles import get_profile_by_id

def _source_weights(profile_slug: str) -> dict[str, float]:
    return {s["name"]: float(s.get("weight", 1.0)) for s in load_profile_sources(profile_slug)}


def select_topics(
    profile_id: int, limit: int | None = None, lookback_days: int | None = None,
) -> list[dict[str, Any]]:
    with connect() as conn:
        profile = get_profile_by_id(conn, profile_id)
    if not profile:
        raise ValueError(f"no profile {profile_id}")

    cfg = settings()
    limit = limit or profile.get("posts_per_day") or cfg.get("posts_per_day", 3)
    select_cfg = cfg.get("select", {})
    lookback = lookback_days or select_cfg.get("lookback_days", 14)
    weights = _source_weights(profile["slug"])

    # ... interest/entities/actions unchanged (global virality tuning, not
    # profile-specific per the spec — only sources/prompt are profile-owned) ...

    with connect() as conn:
        used = used_item_ids(conn, lookback, profile_id)
        pinned_ids = [i for i in pinned_item_ids(conn) if i not in used]
        pinned = get_items(conn, pinned_ids)
        skip = used | set(pinned_ids)
        candidates = [it for it in recent_items(conn, lookback, profile_id) if it["id"] not in skip]
        threads = open_threads(conn, profile_id)
    # ... rest of the function body unchanged, `weights` now profile-scoped ...
```

(`pinned_item_ids`/`get_items` stay global for now — pins are a dashboard
operator action, not yet profile-scoped; flag this as a follow-up rather
than expanding this task's scope further, consistent with the spec's
explicit non-goals.)

- [ ] **Step 4: Update `generate/runner.py` to load the profile's prompt**

Find where the current generation prompt is assembled (likely passed to
`generate_post` from `generator.py`) and thread `load_prompt(profile["slug"])`
into it as the profile-specific style-guide text prepended to the
structural prompt `generator.py` builds. Read `generate/runner.py` and
`generate/generator.py` together before editing — the exact injection point
depends on how `build_cli_prompt`/`build_user_prompt` are currently
structured; this plan specifies the *what* (profile prompt gets prepended)
and *where* (runner resolves it, generator accepts it as a parameter), not
a byte-exact diff, since it depends on code not yet re-read at plan-writing
time. Add a `profile_prompt: str = ""` parameter to `generate_post` in
`generator.py` and prepend it to whichever prompt-building function is
active for the configured backend.

- [ ] **Step 5: Update `services/pipeline_service.py` and `jobs/registry.py`**

```python
# pipeline_service.py
def run_ingest_service(profile_id: int, since: str | None = None, limit: int | None = None) -> dict[str, Any]:
    return run_ingest(profile_id, since=since, limit=limit)


def run_generate_service(
    profile_id: int, limit: int | None = None, on_progress: Callable[..., None] | None = None,
) -> list[dict[str, Any]]:
    return run_generate(profile_id, limit=limit, on_progress=on_progress)
```

```python
# jobs/registry.py — job payloads now carry profile_id
JOB_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "full_run": lambda payload: pipeline_service.run_full_pipeline_service(
        profile_id=payload["profile_id"], force=True,
    ),
    "ingest": lambda payload: pipeline_service.run_ingest_service(profile_id=payload["profile_id"]),
    "generate": lambda payload: pipeline_service.run_generate_service(profile_id=payload["profile_id"]),
    # ... generate_from_item / render_post are already per-item/per-post,
    # which already carry an implicit profile via the item/post row itself
    # once Task 4's schema is in place — leave those two handlers unchanged.
}
```

(`run_full_pipeline_service` itself, in `orchestrate/runner.py`, needs the
same `profile_id` threading — update it alongside this step; it calls
`run_ingest`/`select_topics`/`run_generate` internally and its own
idempotency guard (`runs` table) is now `(profile_id, run_date)`-scoped per
Task 4.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/generate/ tests/services/ tests/jobs/ -v`
Expected: PASS

- [ ] **Step 7: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS. Any remaining failures at this point should be isolated to
the dashboard/API/CLI call sites that invoke `run_ingest_service`/
`run_generate_service` without a `profile_id` yet — those are explicitly
sub-project C's job (the dashboard needs a profile selector before it can
supply this), not this plan's. If the CLI (`cli.py`) breaks, give it a
minimal fix: default to the `fork-ai` profile's id (resolved via
`get_profile(conn, "fork-ai")`) so `claudeshorts run`/`ingest`/`generate`
keep working single-profile until a `--profile` flag is added later
(explicitly out of scope here — note it as a follow-up, don't build the
flag now).

- [ ] **Step 8: Commit**

```bash
git add claudeshorts/generate/select.py claudeshorts/generate/runner.py claudeshorts/generate/generator.py claudeshorts/services/pipeline_service.py claudeshorts/jobs/registry.py claudeshorts/orchestrate/runner.py claudeshorts/cli.py tests/generate/ tests/services/ tests/jobs/
git commit -m "feat: profile-scope ingest/select/generate services, load per-profile sources and prompt"
```

---

### Task 7: `auto_publish` headless mechanism in `posts_service`

**Wave:** 3 (depends on Task 2)

**Files:**
- Modify: `claudeshorts/services/posts_service.py`
- Test: extend `tests/services/test_posts_service.py`

**Interfaces:**
- Produces: `render_post_service`'s caller-visible behavior changes — when
  the rendered post's profile has `auto_publish = true`, the post is
  exported immediately (same code path `posts_service.export_now` already
  uses for a manual Approve) instead of being left in `rendered` status.
- Consumes: `store.profiles.get_profile_by_id` (Task 2).

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_posts_service.py — add
def test_render_then_persist_auto_exports_when_profile_auto_publish_true(db_conn, monkeypatch):
    profile_id = upsert_profile(db_conn, slug="headless-profile", display_name="Headless")
    set_auto_publish(db_conn, profile_id, True)
    post_id = insert_post(db_conn, item_ids=[1], title="T", slides=[], profile_id=profile_id)
    db_conn.commit()

    exported = []
    monkeypatch.setattr(
        "claudeshorts.services.posts_service.export_now",
        lambda pid: exported.append(pid),
    )

    maybe_auto_publish(db_conn, post_id)

    assert exported == [post_id]


def test_maybe_auto_publish_noop_when_profile_auto_publish_false(db_conn, monkeypatch):
    profile_id = upsert_profile(db_conn, slug="reviewed-profile", display_name="Reviewed")
    post_id = insert_post(db_conn, item_ids=[1], title="T", slides=[], profile_id=profile_id)
    db_conn.commit()

    exported = []
    monkeypatch.setattr(
        "claudeshorts.services.posts_service.export_now",
        lambda pid: exported.append(pid),
    )

    maybe_auto_publish(db_conn, post_id)

    assert exported == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_posts_service.py -v`
Expected: FAIL — `maybe_auto_publish` doesn't exist yet.

- [ ] **Step 3: Implement `maybe_auto_publish` and wire it into the render path**

In `claudeshorts/services/posts_service.py`, add:

```python
from ..store.profiles import get_profile_by_id


def maybe_auto_publish(conn, post_id: int) -> bool:
    """If the post's profile has auto_publish on, export immediately instead
    of waiting for a manual Approve. Returns True if it exported."""
    post = get_post(conn, post_id)
    if not post or not post.get("profile_id"):
        return False
    profile = get_profile_by_id(conn, post["profile_id"])
    if not profile or not profile["auto_publish"]:
        return False
    export_now(post_id)
    return True
```

In `pipeline_service.render_post_service` (Task 6 already touched this
file's other functions; this is an additional, independent edit — safe to
make even if Task 6 hasn't merged yet, since it only adds a call at the end
of an existing function), call it after `assemble_review`:

```python
def render_post_service(post_id: int) -> dict[str, Any]:
    with connect() as conn:
        post = get_post(conn, post_id)
    if not post:
        raise ValueError(f"no post {post_id}")
    result = render_post(post)
    review_dir = assemble_review(post, result)
    with connect() as conn:
        posts_service.maybe_auto_publish(conn, post_id)
    return {
        "frames": result.get("frames"),
        "duration_ms": result.get("duration_ms"),
        "audio_mode": result.get("audio_mode"),
        "review_dir": review_dir,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_posts_service.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/services/posts_service.py claudeshorts/services/pipeline_service.py tests/services/test_posts_service.py
git commit -m "feat: auto-export rendered posts when their profile has auto_publish enabled"
```

---

### Task 8: Scheduler seeds one schedule set per active profile

**Wave:** 4 (depends on Task 2, Task 6)

**Files:**
- Modify: `claudeshorts/scheduling/scheduler.py`
- Test: extend `tests/scheduling/test_scheduler.py`

**Interfaces:**
- Produces: on boot, `seed_default_schedules()` (or whatever the existing
  function is named — read the current file first) creates a
  `full_run`/`drain_scheduled_posts`/`weekly_report` schedule **per active
  profile** (name disambiguated per profile, e.g. `"full_run:fork-ai"`,
  `"full_run:midnight-curiosity"`), each with `payload={"profile_id": ...}`.
- Consumes: `store.profiles.list_profiles(conn, active_only=True)` (Task 2).

- [ ] **Step 1: Write the failing test**

```python
# tests/scheduling/test_scheduler.py — add
def test_seed_default_schedules_creates_one_full_run_per_active_profile(db_conn):
    p1 = upsert_profile(db_conn, slug="profile-one", display_name="One")
    p2 = upsert_profile(db_conn, slug="profile-two", display_name="Two")
    inactive = upsert_profile(db_conn, slug="profile-three", display_name="Three")
    db_conn.execute("UPDATE profiles SET active = false WHERE id = %s", (inactive,))
    db_conn.commit()

    seed_default_schedules()

    rows = db_conn.execute("SELECT name, payload FROM schedules WHERE job_type = 'full_run'").fetchall()
    names = {r["name"] for r in rows}
    assert "full_run:profile-one" in names
    assert "full_run:profile-two" in names
    assert "full_run:profile-three" not in names
    payloads = {r["name"]: r["payload"] for r in rows}
    assert payloads["full_run:profile-one"]["profile_id"] == p1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scheduling/test_scheduler.py -v`
Expected: FAIL — current seeding creates one unscoped `"full_run"` schedule,
not one per profile.

- [ ] **Step 3: Update the seeding function**

Read `claudeshorts/scheduling/scheduler.py`'s current seeding function in
full before editing (its exact current shape wasn't re-read while writing
this plan). Restructure it to loop over
`store.profiles.list_profiles(conn, active_only=True)` and call
`scheduling.store.upsert_schedule` once per profile per job type, with the
schedule `name` including the profile slug (so re-seeding stays idempotent
per profile via the existing `ON CONFLICT (name)` behavior) and
`payload={"profile_id": profile["id"]}`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scheduling/ -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS (this is the last task in the plan — if this passes, the
full 226+-test suite covering everything Tasks 1-8 touched should be green
end to end)

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/scheduling/scheduler.py tests/scheduling/test_scheduler.py
git commit -m "feat: scheduler seeds full_run/drain/weekly_report schedules per active profile"
```

---

## Self-review

**Spec coverage:** `profiles` table + `profile_id` FKs (Task 1) ✓;
`store/profiles.py` CRUD (Task 2) ✓; `config/profiles/<slug>/` restructure
+ browser-profile merge (Task 3) ✓; store/ingest profile threading (Task 4)
✓; migration/backfill (Task 5) ✓; ingest/select/generate profile-scoping
incl. per-profile prompt (Task 6) ✓; `auto_publish` headless mechanism
(Task 7) ✓; per-profile scheduling (Task 8) ✓. Dashboard/API profile
filtering and real analytics are correctly left to sub-projects B/C, not
silently dropped — they're named as explicit non-goals in Global Constraints.

**Placeholder scan:** no TBD/TODO. Two steps (Task 6 Step 4, Task 8 Step 3)
explicitly say "read the file first, exact shape depends on code not
re-read while writing this plan" rather than inventing a byte-exact diff
for code this plan's author hadn't opened — that's an intentional,
disclosed judgment call for an implementer to resolve against real code,
not a placeholder for missing design thinking (the *what* and *where* are
fully specified in both cases).

**Type/name consistency:** `profile_id: int` used consistently as a
required parameter name across all store/service functions in Tasks 4, 6,
7. `store.profiles.get_profile_by_id` (Task 2) is the one function later
tasks (6, 7) rely on for slug/config resolution — name matches everywhere
it's referenced. `browser.profiles.list_profiles()` (filesystem-based,
Task 3) and `store.profiles.list_profiles()` (DB-based, Task 2) are a
deliberate, flagged name collision — not a mismatch, called out explicitly
in Task 3's Interfaces section so nobody "fixes" it as a bug later without
reading why.
