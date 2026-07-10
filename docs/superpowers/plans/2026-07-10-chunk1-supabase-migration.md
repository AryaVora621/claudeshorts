# Chunk 1: Supabase Schema + SQLite Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace claudeshorts' SQLite datastore with the new `claudeshorts` Supabase Postgres project (id `nddlutmilajkqtoygmfi`, region `us-east-1`), migrating existing data, with zero changes required in any of the 8 files that call the `store/*.py` layer.

**Architecture:** `claudeshorts/store/db.py` switches from `sqlite3` to `psycopg` (psycopg3) against Supabase's Session Pooler connection string. Every `store/*.py` module keeps its exact function signatures; only SQL dialect and row handling inside them changes (placeholders `?`/`:name` → `%s`/`%(name)s`, `INSERT OR IGNORE`/`OR REPLACE` → `ON CONFLICT`, `lastrowid` → `RETURNING id`, `datetime('now', ...)` → `now() - interval`). A one-time script copies existing rows across, preserving IDs.

**Tech Stack:** Python 3.11+, `psycopg[binary]>=3.2` (prebuilt wheels, including ARM/Raspberry Pi), Supabase Postgres 17.

## Global Constraints

- Python 3.11+, type hints everywhere, PEP 8 (per `CLAUDE.md`).
- No comments explaining *what* code does — only *why*, and only when non-obvious.
- Secrets only in `.env` (gitignored); `.env.example` documents the variable name, never a real value.
- The 8 existing callers of the store layer must not change:
  `claudeshorts/dashboard/app.py`, `claudeshorts/dashboard/jobs.py`,
  `claudeshorts/generate/runner.py`, `claudeshorts/generate/select.py`,
  `claudeshorts/ingest/runner.py`, `claudeshorts/orchestrate/runner.py`,
  `claudeshorts/publish/exporter.py`, `claudeshorts/review/queue.py`.
- `data/app.db` is never deleted or written to by this work — read-only source for migration, kept as a local backup.
- Full spec: `docs/superpowers/specs/2026-07-10-chunk1-supabase-migration-design.md`.

---

## File Structure

- Modify: `pyproject.toml`, `requirements.txt` — add `psycopg[binary]>=3.2`, remove nothing (sqlite3 is stdlib, no removal needed).
- Modify: `.env.example` — add `SUPABASE_DB_URL`.
- Modify: `claudeshorts/config.py` — add `supabase_db_url()` accessor.
- Modify: `claudeshorts/store/db.py` — full rewrite: Postgres `SCHEMA`, `connect()` via psycopg, drop `_apply_migrations`/`init_db` SQLite-specific logic in favor of a single idempotent `CREATE TABLE IF NOT EXISTS` schema (Postgres already supports `IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS`, so the additive-migration list collapses into the schema itself).
- Modify: `claudeshorts/store/items.py`, `posts.py`, `threads.py`, `pins.py`, `runs.py`, `jobs.py` — dialect conversion only, same public signatures.
- Create: `scripts/migrate_sqlite_to_supabase.py` — one-time migration script.
- Create: `tests/store/conftest.py` — pytest fixture providing a real Postgres connection (Supabase project, isolated by truncating tables between tests).
- Create: `tests/store/test_items.py`, `test_posts.py`, `test_threads.py`, `test_pins.py`, `test_runs.py`, `test_jobs.py` — one test file per store module, covering each public function.

---

### Task 1: Add psycopg dependency, config accessor, and `.env` entry

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `claudeshorts/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `claudeshorts.config.supabase_db_url() -> str` — reads `SUPABASE_DB_URL` from the environment, raises `RuntimeError` with a clear message if unset.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from __future__ import annotations

import pytest

from claudeshorts import config


def test_supabase_db_url_reads_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://user:pass@host:5432/postgres")
    assert config.supabase_db_url() == "postgresql://user:pass@host:5432/postgres"


def test_supabase_db_url_missing_raises(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_DB_URL"):
        config.supabase_db_url()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with "AttributeError: module 'claudeshorts.config' has no attribute 'supabase_db_url'"

- [ ] **Step 3: Add the dependency**

In `pyproject.toml`, add to `dependencies`:
```toml
    "psycopg[binary]>=3.2",
```

In `requirements.txt`, add a line:
```
psycopg[binary]>=3.2
```

- [ ] **Step 4: Add `SUPABASE_DB_URL` to `.env.example`**

Append to `.env.example`:
```bash
# Required once the Supabase datastore migration lands. Use the Session
# Pooler connection string from Supabase project settings > Database
# (not the Transaction pooler — this app holds long-lived connections).
# SUPABASE_DB_URL=postgresql://postgres.xxxx:PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres
```

- [ ] **Step 5: Implement `supabase_db_url()`**

In `claudeshorts/config.py`, add near the top-level imports:
```python
import os
```

Add function (after `sources()`):
```python
def supabase_db_url() -> str:
    """The Supabase Postgres connection string (Session Pooler), from env."""
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError(
            "SUPABASE_DB_URL is not set. Copy .env.example to .env and fill "
            "in the Session Pooler connection string from your Supabase "
            "project's Database settings."
        )
    return url
```

- [ ] **Step 6: Install the dependency and run test to verify it passes**

Run: `.venv/bin/pip install -e . && pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml requirements.txt .env.example claudeshorts/config.py tests/test_config.py
git commit -m "feat: add psycopg dependency and SUPABASE_DB_URL config accessor"
```

---

### Task 2: Rewrite `store/db.py` for Postgres

**Files:**
- Modify: `claudeshorts/store/db.py`
- Test: `tests/store/conftest.py` (created here, used by all later store tests)

**Interfaces:**
- Consumes: `claudeshorts.config.supabase_db_url() -> str` (Task 1)
- Produces: `connect() -> psycopg.Connection` (dict-row factory, used as a context manager exactly like the old `sqlite3.Connection` — commits on clean exit, rolls back on exception). `init_db() -> None`.

- [ ] **Step 1: Write the failing test (conftest + a schema smoke test)**

```python
# tests/store/conftest.py
from __future__ import annotations

import pytest

from claudeshorts.store import db

_TABLES = ("post_threads", "pins", "jobs", "runs", "posts", "threads", "items")


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate all tables before each test so tests are independent."""
    db.init_db()
    with db.connect() as conn:
        for t in _TABLES:
            conn.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE")
    yield
```

```python
# tests/store/test_db.py
from __future__ import annotations

from claudeshorts.store import db


def test_connect_returns_working_connection():
    with db.connect() as conn:
        row = conn.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_db.py -v`
Expected: FAIL — `SUPABASE_DB_URL` unset in test env, or old sqlite-based `connect()` signature mismatch.

Before proceeding, export a real test connection string for local runs (this is the actual Supabase project created for this work):
```bash
export SUPABASE_DB_URL="postgresql://postgres.nddlutmilajkqtoygmfi:<DB_PASSWORD>@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
```
(`<DB_PASSWORD>` is the database password set when the project was created — retrieve it from the Supabase dashboard's Database settings, or reset it there if not on hand. Put this export in `.env` for local dev.)

- [ ] **Step 3: Implement the Postgres schema and connection helper**

Replace the entire contents of `claudeshorts/store/db.py`:

```python
"""Postgres (Supabase) schema definition and connection helpers.

The schema is additive: every statement is `CREATE TABLE IF NOT EXISTS` /
`ADD COLUMN IF NOT EXISTS`, so `init_db()` is safe to call on every startup.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from ..config import supabase_db_url

# --- Schema ----------------------------------------------------------------
# items:        raw normalized news items from ingestion (Phase 1)
# posts:        a generated piece of content + its lifecycle status (Phase 2+)
# threads:      an ongoing storyline that posts attach to (content memory)
# post_threads: many-to-many link between posts and threads
SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            BIGSERIAL PRIMARY KEY,
    source        TEXT        NOT NULL,
    url           TEXT,
    title         TEXT        NOT NULL,
    summary       TEXT,
    published_at  TEXT,
    content_hash  TEXT        NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_content_hash ON items(content_hash);
CREATE INDEX IF NOT EXISTS idx_items_published_at ON items(published_at);

CREATE TABLE IF NOT EXISTS posts (
    id            BIGSERIAL PRIMARY KEY,
    item_ids      JSONB,
    status        TEXT        NOT NULL DEFAULT 'draft',
    title         TEXT,
    slides_json   JSONB,
    theme_json    JSONB,
    captions_json JSONB,
    review_note   TEXT,
    published_at  TEXT,
    scheduled_for TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);

CREATE TABLE IF NOT EXISTS threads (
    id            BIGSERIAL PRIMARY KEY,
    slug          TEXT        NOT NULL UNIQUE,
    title         TEXT        NOT NULL,
    summary       TEXT,
    status        TEXT        NOT NULL DEFAULT 'ongoing',
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_updated  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS post_threads (
    post_id    BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    thread_id  BIGINT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, thread_id)
);

CREATE TABLE IF NOT EXISTS runs (
    id            BIGSERIAL PRIMARY KEY,
    run_date      TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'running',
    posts_created INTEGER     NOT NULL DEFAULT 0,
    detail        TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(run_date);

CREATE TABLE IF NOT EXISTS pins (
    item_id    BIGINT PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    note       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
    id               BIGSERIAL PRIMARY KEY,
    name             TEXT        NOT NULL,
    status           TEXT        NOT NULL DEFAULT 'running',
    phase_index      INTEGER     NOT NULL DEFAULT 0,
    phase_total      INTEGER     NOT NULL DEFAULT 0,
    phase_label      TEXT        NOT NULL DEFAULT '',
    progress_current INTEGER     NOT NULL DEFAULT 0,
    progress_total   INTEGER     NOT NULL DEFAULT 0,
    progress_label   TEXT        NOT NULL DEFAULT '',
    log              TEXT        NOT NULL DEFAULT '',
    error            TEXT,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ
);
"""


def connect() -> psycopg.Connection:
    """Open a connection with sensible defaults (dict rows, fail-fast timeouts).

    Used as a context manager exactly like the old sqlite3 connections: commits
    on clean exit, rolls back on exception.
    """
    return psycopg.connect(
        supabase_db_url(),
        row_factory=dict_row,
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )


def init_db() -> None:
    """Create the schema if needed. Idempotent."""
    with connect() as conn:
        conn.execute(SCHEMA)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_db.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/store/db.py tests/store/conftest.py tests/store/test_db.py
git commit -m "feat: rewrite store/db.py schema+connection for Postgres/Supabase"
```

---

### Task 3: Convert `store/items.py` to Postgres dialect

**Files:**
- Modify: `claudeshorts/store/items.py`
- Test: `tests/store/test_items.py`

**Interfaces:**
- Consumes: `claudeshorts.store.db.connect()` (Task 2)
- Produces: unchanged public API — `insert_item`, `insert_manual_item`, `count_items`, `get_item`, `latest_items`, `get_items`, `recent_items` (same names, params, return types as before; first param type is now `psycopg.Connection` instead of `sqlite3.Connection`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/store/test_items.py
from __future__ import annotations

from claudeshorts.store import db, items


def test_insert_item_then_dedupe():
    with db.connect() as conn:
        item = {
            "source": "test", "url": "https://a", "title": "Title A",
            "summary": "sum", "published_at": None, "content_hash": "hash-a",
        }
        assert items.insert_item(conn, item) is True
        assert items.insert_item(conn, item) is False
        assert items.count_items(conn) == 1


def test_get_item_and_latest_items():
    with db.connect() as conn:
        items.insert_item(conn, {
            "source": "test", "url": None, "title": "T1", "summary": None,
            "published_at": None, "content_hash": "h1",
        })
        row_id = conn.execute("SELECT id FROM items WHERE content_hash = 'h1'").fetchone()["id"]
        got = items.get_item(conn, row_id)
        assert got["title"] == "T1"
        latest = items.latest_items(conn, limit=10)
        assert len(latest) == 1


def test_get_items_preserves_order():
    with db.connect() as conn:
        ids = []
        for h in ("h1", "h2", "h3"):
            items.insert_item(conn, {
                "source": "test", "url": None, "title": h, "summary": None,
                "published_at": None, "content_hash": h,
            })
            ids.append(conn.execute(
                "SELECT id FROM items WHERE content_hash = %s", (h,)
            ).fetchone()["id"])
        fetched = items.get_items(conn, [ids[2], ids[0]])
        assert [r["id"] for r in fetched] == [ids[2], ids[0]]


def test_insert_manual_item_idempotent_by_content():
    with db.connect() as conn:
        id1, created1 = items.insert_manual_item(conn, title="Hello", url="https://x")
        id2, created2 = items.insert_manual_item(conn, title="Hello", url="https://x")
        assert created1 is True
        assert created2 is False
        assert id1 == id2


def test_recent_items_filters_by_days():
    with db.connect() as conn:
        items.insert_item(conn, {
            "source": "test", "url": None, "title": "Recent", "summary": None,
            "published_at": None, "content_hash": "recent-1",
        })
        recent = items.recent_items(conn, days=1)
        assert len(recent) == 1
        assert recent[0]["title"] == "Recent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_items.py -v`
Expected: FAIL (sqlite-style `?`/`:name` placeholders are invalid Postgres syntax; `psycopg.errors.SyntaxError` or similar)

- [ ] **Step 3: Rewrite `claudeshorts/store/items.py`**

```python
"""Data-access helpers for the `items` table (raw ingested news)."""

from __future__ import annotations

from typing import Any

import psycopg

ITEM_FIELDS = ("source", "url", "title", "summary", "published_at", "content_hash")


def insert_item(conn: psycopg.Connection, item: dict[str, Any]) -> bool:
    """Insert an item, ignoring duplicates (by unique content_hash).

    Returns True if a new row was stored, False if it was a duplicate.
    """
    cur = conn.execute(
        "INSERT INTO items "
        "(source, url, title, summary, published_at, content_hash) "
        "VALUES (%(source)s, %(url)s, %(title)s, %(summary)s, "
        "%(published_at)s, %(content_hash)s) "
        "ON CONFLICT (content_hash) DO NOTHING",
        {k: item.get(k) for k in ITEM_FIELDS},
    )
    return cur.rowcount > 0


def insert_manual_item(
    conn: psycopg.Connection,
    *,
    title: str,
    url: str | None = None,
    summary: str | None = None,
    source: str = "manual",
) -> tuple[int, bool]:
    """Insert an operator-supplied article (dashboard). Idempotent by content.

    Returns ``(item_id, created)`` — for an existing duplicate the prior id is
    returned with ``created=False`` so the caller can still pin/generate it.
    """
    from ..ingest.fetchers import content_hash  # lazy: avoids import cycle

    h = content_hash(url, title)
    created = insert_item(conn, {
        "source": source, "url": url, "title": title.strip(),
        "summary": summary, "published_at": None, "content_hash": h,
    })
    row = conn.execute("SELECT id FROM items WHERE content_hash = %s", (h,)).fetchone()
    return int(row["id"]), created


def count_items(conn: psycopg.Connection) -> int:
    """Total rows currently in `items`."""
    return conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]


def get_item(conn: psycopg.Connection, item_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM items WHERE id = %s", (item_id,)).fetchone()
    return dict(row) if row else None


def latest_items(conn: psycopg.Connection, limit: int = 100) -> list[dict[str, Any]]:
    """Most recently fetched items, newest first (for the dashboard browser)."""
    rows = conn.execute(
        "SELECT * FROM items ORDER BY COALESCE(published_at, fetched_at::text) DESC, "
        "id DESC LIMIT %s",
        (int(limit),),
    ).fetchall()
    return [dict(r) for r in rows]


def get_items(conn: psycopg.Connection, ids: list[int]) -> list[dict[str, Any]]:
    """Fetch items by id, preserving the given order."""
    if not ids:
        return []
    rows = conn.execute(
        "SELECT * FROM items WHERE id = ANY(%s)", (list(ids),)
    ).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def recent_items(conn: psycopg.Connection, days: int) -> list[dict[str, Any]]:
    """Items fetched within the last `days`, newest first (for selection)."""
    rows = conn.execute(
        "SELECT * FROM items WHERE fetched_at >= now() - (%s || ' days')::interval "
        "ORDER BY COALESCE(published_at, fetched_at::text) DESC",
        (int(days),),
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_items.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/store/items.py tests/store/test_items.py
git commit -m "feat: convert store/items.py to Postgres dialect"
```

---

### Task 4: Convert `store/posts.py` to Postgres dialect

**Files:**
- Modify: `claudeshorts/store/posts.py`
- Test: `tests/store/test_posts.py`

**Interfaces:**
- Consumes: `db.connect()` (Task 2)
- Produces: unchanged public API — `insert_post`, `get_post`, `recent_posts`, `posts_by_status`, `all_posts`, `status_counts`, `set_schedule`, `scheduled_posts`, `due_posts`, `used_item_ids`, `set_status`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/store/test_posts.py
from __future__ import annotations

from claudeshorts.store import db, posts


def _mk(conn, **overrides):
    kwargs = dict(item_ids=[1, 2], title="T", slides={"a": 1}, captions={"b": 2})
    kwargs.update(overrides)
    return posts.insert_post(conn, **kwargs)


def test_insert_and_get_post_round_trips_json():
    with db.connect() as conn:
        post_id = _mk(conn)
        got = posts.get_post(conn, post_id)
        assert got["item_ids"] == [1, 2]
        assert got["slides"] == {"a": 1}
        assert got["captions"] == {"b": 2}
        assert got["status"] == "draft"


def test_status_counts_and_posts_by_status():
    with db.connect() as conn:
        _mk(conn)
        p2 = _mk(conn)
        posts.set_status(conn, p2, "approved")
        counts = posts.status_counts(conn)
        assert counts == {"draft": 1, "approved": 1}
        approved = posts.posts_by_status(conn, "approved")
        assert [p["id"] for p in approved] == [p2]


def test_schedule_and_due_posts():
    with db.connect() as conn:
        p1 = _mk(conn)
        posts.set_status(conn, p1, "approved")
        posts.set_schedule(conn, p1, "2020-01-01")
        assert [p["id"] for p in posts.scheduled_posts(conn)] == [p1]
        assert [p["id"] for p in posts.due_posts(conn, "2099-01-01")] == [p1]
        assert posts.due_posts(conn, "2000-01-01") == []


def test_used_item_ids_aggregates_recent_posts():
    with db.connect() as conn:
        _mk(conn, item_ids=[10, 20])
        _mk(conn, item_ids=[20, 30])
        assert posts.used_item_ids(conn, days=1) == {10, 20, 30}


def test_recent_posts_and_all_posts():
    with db.connect() as conn:
        _mk(conn)
        _mk(conn)
        assert len(posts.recent_posts(conn, days=1)) == 2
        assert len(posts.all_posts(conn, limit=200)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_posts.py -v`
Expected: FAIL (sqlite placeholders/`lastrowid` invalid against Postgres)

- [ ] **Step 3: Rewrite `claudeshorts/store/posts.py`**

```python
"""Data-access helpers for the `posts` table (generated content + lifecycle)."""

from __future__ import annotations

from typing import Any

import psycopg


def _row_to_post(row: dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    d["item_ids"] = d.get("item_ids") or []
    d["slides"] = d.get("slides_json")
    d["theme"] = d.get("theme_json")
    d["captions"] = d.get("captions_json")
    return d


def insert_post(
    conn: psycopg.Connection,
    *,
    item_ids: list[int],
    title: str,
    slides: Any,
    captions: Any,
    theme: Any = None,
    status: str = "draft",
) -> int:
    """Insert a generated post; returns the new post id."""
    row = conn.execute(
        "INSERT INTO posts "
        "(item_ids, status, title, slides_json, theme_json, captions_json) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (
            psycopg.types.json.Jsonb(item_ids), status, title,
            psycopg.types.json.Jsonb(slides), psycopg.types.json.Jsonb(theme),
            psycopg.types.json.Jsonb(captions),
        ),
    ).fetchone()
    return int(row["id"])


def get_post(conn: psycopg.Connection, post_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM posts WHERE id = %s", (post_id,)).fetchone()
    return _row_to_post(row) if row else None


def recent_posts(conn: psycopg.Connection, days: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM posts WHERE created_at >= now() - (%s || ' days')::interval "
        "ORDER BY created_at DESC",
        (int(days),),
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def posts_by_status(conn: psycopg.Connection, status: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM posts WHERE status = %s ORDER BY created_at DESC", (status,)
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def all_posts(conn: psycopg.Connection, limit: int = 200) -> list[dict[str, Any]]:
    """Every post, newest first (for the dashboard browser)."""
    rows = conn.execute(
        "SELECT * FROM posts ORDER BY created_at DESC, id DESC LIMIT %s", (int(limit),)
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def status_counts(conn: psycopg.Connection) -> dict[str, int]:
    """Map of status -> count across all posts (for the overview tiles)."""
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM posts GROUP BY status"
    ).fetchall()
    return {r["status"]: r["n"] for r in rows}


def set_schedule(
    conn: psycopg.Connection, post_id: int, scheduled_for: str | None
) -> None:
    """Set (or clear, with None) a post's target publish date (YYYY-MM-DD)."""
    conn.execute(
        "UPDATE posts SET scheduled_for = %s WHERE id = %s", (scheduled_for, post_id)
    )


def scheduled_posts(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Posts with a target publish date set, soonest first."""
    rows = conn.execute(
        "SELECT * FROM posts WHERE scheduled_for IS NOT NULL "
        "ORDER BY scheduled_for ASC, id ASC"
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def due_posts(conn: psycopg.Connection, on_date: str) -> list[dict[str, Any]]:
    """Approved posts whose scheduled_for has arrived (<= on_date)."""
    rows = conn.execute(
        "SELECT * FROM posts WHERE status = 'approved' "
        "AND scheduled_for IS NOT NULL AND scheduled_for <= %s "
        "ORDER BY scheduled_for ASC, id ASC",
        (on_date,),
    ).fetchall()
    return [_row_to_post(r) for r in rows]


def used_item_ids(conn: psycopg.Connection, days: int) -> set[int]:
    """item ids already consumed by recent posts (for selection dedupe)."""
    ids: set[int] = set()
    for post in recent_posts(conn, days):
        ids.update(post["item_ids"])
    return ids


def set_status(
    conn: psycopg.Connection, post_id: int, status: str,
    *, note: str | None = None, published_at: str | None = None,
) -> None:
    conn.execute(
        "UPDATE posts SET status = %s, "
        "review_note = COALESCE(%s, review_note), "
        "published_at = COALESCE(%s, published_at) WHERE id = %s",
        (status, note, published_at, post_id),
    )
```

Note: `slides_json`/`theme_json`/`captions_json` are now native `JSONB` columns (Task 2's schema), so psycopg returns them already decoded as Python objects on read — no `json.loads` needed in `_row_to_post`, and writes wrap values in `psycopg.types.json.Jsonb(...)` so psycopg serializes them correctly.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_posts.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/store/posts.py tests/store/test_posts.py
git commit -m "feat: convert store/posts.py to Postgres dialect with native JSONB"
```

---

### Task 5: Convert `store/threads.py` to Postgres dialect

**Files:**
- Modify: `claudeshorts/store/threads.py`
- Test: `tests/store/test_threads.py`

**Interfaces:**
- Consumes: `db.connect()` (Task 2), reads `posts` table (Task 4's schema)
- Produces: unchanged public API — `open_threads`, `get_thread_by_slug`, `upsert_thread`, `link_post_thread`, `posts_for_thread`, `threads_with_posts`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/store/test_threads.py
from __future__ import annotations

from claudeshorts.store import db, posts, threads


def test_upsert_thread_creates_then_updates():
    with db.connect() as conn:
        tid1 = threads.upsert_thread(conn, slug="gpt-5", title="GPT-5", summary="s1")
        tid2 = threads.upsert_thread(conn, slug="gpt-5", title="GPT-5 v2", summary="s2")
        assert tid1 == tid2
        got = threads.get_thread_by_slug(conn, "gpt-5")
        assert got["title"] == "GPT-5 v2"


def test_open_threads_only_ongoing():
    with db.connect() as conn:
        threads.upsert_thread(conn, slug="a", title="A", summary=None)
        assert len(threads.open_threads(conn)) == 1


def test_link_post_thread_and_posts_for_thread():
    with db.connect() as conn:
        post_id = posts.insert_post(
            conn, item_ids=[1], title="T", slides={}, captions={}
        )
        tid = threads.upsert_thread(conn, slug="a", title="A", summary=None)
        threads.link_post_thread(conn, post_id, tid)
        linked = threads.posts_for_thread(conn, tid)
        assert [p["id"] for p in linked] == [post_id]


def test_threads_with_posts_nests_posts():
    with db.connect() as conn:
        post_id = posts.insert_post(
            conn, item_ids=[1], title="T", slides={}, captions={}
        )
        tid = threads.upsert_thread(conn, slug="a", title="A", summary=None)
        threads.link_post_thread(conn, post_id, tid)
        out = threads.threads_with_posts(conn)
        assert out[0]["posts"][0]["id"] == post_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_threads.py -v`
Expected: FAIL (sqlite placeholders/`lastrowid` invalid against Postgres)

- [ ] **Step 3: Rewrite `claudeshorts/store/threads.py`**

```python
"""Data-access helpers for `threads` + `post_threads` (content memory).

A thread is an ongoing storyline (e.g. "gpt-5-launch"). Posts attach to threads
so the pipeline can detect follow-ups and build on prior coverage.
"""

from __future__ import annotations

from typing import Any

import psycopg


def open_threads(conn: psycopg.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM threads WHERE status = 'ongoing' ORDER BY last_updated DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_thread_by_slug(conn: psycopg.Connection, slug: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM threads WHERE slug = %s", (slug,)).fetchone()
    return dict(row) if row else None


def upsert_thread(
    conn: psycopg.Connection, *, slug: str, title: str, summary: str | None,
) -> int:
    """Create or refresh a thread by slug; returns its id. Bumps last_updated."""
    row = conn.execute(
        "INSERT INTO threads (slug, title, summary) VALUES (%s, %s, %s) "
        "ON CONFLICT (slug) DO UPDATE SET "
        "title = EXCLUDED.title, summary = EXCLUDED.summary, "
        "status = 'ongoing', last_updated = now() "
        "RETURNING id",
        (slug, title, summary),
    ).fetchone()
    return int(row["id"])


def link_post_thread(conn: psycopg.Connection, post_id: int, thread_id: int) -> None:
    conn.execute(
        "INSERT INTO post_threads (post_id, thread_id) VALUES (%s, %s) "
        "ON CONFLICT DO NOTHING",
        (post_id, thread_id),
    )


def posts_for_thread(conn: psycopg.Connection, thread_id: int) -> list[dict[str, Any]]:
    """Posts attached to a thread, newest first (id, title, status, created_at)."""
    rows = conn.execute(
        "SELECT p.id, p.title, p.status, p.created_at FROM posts p "
        "JOIN post_threads pt ON pt.post_id = p.id "
        "WHERE pt.thread_id = %s ORDER BY p.created_at DESC, p.id DESC",
        (thread_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def threads_with_posts(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """All threads (newest activity first), each with its linked posts attached."""
    rows = conn.execute("SELECT * FROM threads ORDER BY last_updated DESC").fetchall()
    out = []
    for r in rows:
        th = dict(r)
        th["posts"] = posts_for_thread(conn, th["id"])
        out.append(th)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_threads.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/store/threads.py tests/store/test_threads.py
git commit -m "feat: convert store/threads.py to Postgres dialect"
```

---

### Task 6: Convert `store/pins.py` to Postgres dialect

**Files:**
- Modify: `claudeshorts/store/pins.py`
- Test: `tests/store/test_pins.py`

**Interfaces:**
- Consumes: `db.connect()` (Task 2), `items` table (Task 3's schema)
- Produces: unchanged public API — `pin_item`, `unpin_item`, `is_pinned`, `pinned_item_ids`, `pinned_items`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/store/test_pins.py
from __future__ import annotations

from claudeshorts.store import db, items, pins


def _mk_item(conn, content_hash):
    items.insert_item(conn, {
        "source": "test", "url": None, "title": "T", "summary": None,
        "published_at": None, "content_hash": content_hash,
    })
    return conn.execute(
        "SELECT id FROM items WHERE content_hash = %s", (content_hash,)
    ).fetchone()["id"]


def test_pin_unpin_and_is_pinned():
    with db.connect() as conn:
        item_id = _mk_item(conn, "h1")
        assert pins.is_pinned(conn, item_id) is False
        pins.pin_item(conn, item_id, note="check this out")
        assert pins.is_pinned(conn, item_id) is True
        pins.unpin_item(conn, item_id)
        assert pins.is_pinned(conn, item_id) is False


def test_pin_item_upserts_note():
    with db.connect() as conn:
        item_id = _mk_item(conn, "h1")
        pins.pin_item(conn, item_id, note="first")
        pins.pin_item(conn, item_id, note="second")
        assert pins.pinned_items(conn)[0]["pin_note"] == "second"


def test_pinned_item_ids_and_pinned_items_order():
    with db.connect() as conn:
        id1 = _mk_item(conn, "h1")
        id2 = _mk_item(conn, "h2")
        pins.pin_item(conn, id1)
        pins.pin_item(conn, id2)
        assert pins.pinned_item_ids(conn) == [id1, id2]
        assert [r["id"] for r in pins.pinned_items(conn)] == [id1, id2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_pins.py -v`
Expected: FAIL (sqlite placeholders invalid against Postgres)

- [ ] **Step 3: Rewrite `claudeshorts/store/pins.py`**

```python
"""Data-access helpers for the `pins` table (operator-flagged items).

A pin marks a raw news item the operator wants turned into a post. Selection
force-includes pinned items ahead of the auto-ranked candidates; the pin is
cleared once a post is generated from that item.
"""

from __future__ import annotations

from typing import Any

import psycopg


def pin_item(conn: psycopg.Connection, item_id: int, note: str | None = None) -> None:
    conn.execute(
        "INSERT INTO pins (item_id, note) VALUES (%s, %s) "
        "ON CONFLICT (item_id) DO UPDATE SET note = EXCLUDED.note",
        (item_id, note),
    )


def unpin_item(conn: psycopg.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM pins WHERE item_id = %s", (item_id,))


def is_pinned(conn: psycopg.Connection, item_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM pins WHERE item_id = %s", (item_id,)
    ).fetchone() is not None


def pinned_item_ids(conn: psycopg.Connection) -> list[int]:
    """Pinned item ids, oldest pin first (FIFO into the generation queue)."""
    rows = conn.execute(
        "SELECT item_id FROM pins ORDER BY created_at ASC, item_id ASC"
    ).fetchall()
    return [r["item_id"] for r in rows]


def pinned_items(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Pinned items joined to their item rows, oldest pin first."""
    rows = conn.execute(
        "SELECT i.*, p.note AS pin_note, p.created_at AS pinned_at "
        "FROM pins p JOIN items i ON i.id = p.item_id "
        "ORDER BY p.created_at ASC, p.item_id ASC"
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_pins.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/store/pins.py tests/store/test_pins.py
git commit -m "feat: convert store/pins.py to Postgres dialect"
```

---

### Task 7: Convert `store/runs.py` to Postgres dialect

**Files:**
- Modify: `claudeshorts/store/runs.py`
- Test: `tests/store/test_runs.py`

**Interfaces:**
- Consumes: `db.connect()` (Task 2)
- Produces: unchanged public API — `latest_run_for_date`, `recent_runs`, `start_run`, `finish_run`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/store/test_runs.py
from __future__ import annotations

from claudeshorts.store import db, runs


def test_start_and_finish_run():
    with db.connect() as conn:
        run_id = runs.start_run(conn, "2026-07-10")
        runs.finish_run(conn, run_id, status="ok", posts_created=3, detail="done")
        latest = runs.latest_run_for_date(conn, "2026-07-10")
        assert latest["status"] == "ok"
        assert latest["posts_created"] == 3
        assert latest["finished_at"] is not None


def test_latest_run_for_date_picks_most_recent():
    with db.connect() as conn:
        runs.start_run(conn, "2026-07-10")
        second = runs.start_run(conn, "2026-07-10")
        latest = runs.latest_run_for_date(conn, "2026-07-10")
        assert latest["id"] == second


def test_recent_runs_orders_newest_first():
    with db.connect() as conn:
        r1 = runs.start_run(conn, "2026-07-09")
        r2 = runs.start_run(conn, "2026-07-10")
        recent = runs.recent_runs(conn, limit=10)
        assert [r["id"] for r in recent] == [r2, r1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_runs.py -v`
Expected: FAIL (sqlite placeholders/`lastrowid` invalid against Postgres)

- [ ] **Step 3: Rewrite `claudeshorts/store/runs.py`**

```python
"""Data-access helpers for the `runs` table (daily pipeline run log).

Backs the once-per-day idempotency guard and a record of what each run did.
"""

from __future__ import annotations

from typing import Any

import psycopg


def latest_run_for_date(conn: psycopg.Connection, run_date: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM runs WHERE run_date = %s ORDER BY id DESC LIMIT 1", (run_date,)
    ).fetchone()
    return dict(row) if row else None


def recent_runs(conn: psycopg.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Most recent pipeline runs, newest first (for the dashboard history)."""
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY id DESC LIMIT %s", (int(limit),)
    ).fetchall()
    return [dict(r) for r in rows]


def start_run(conn: psycopg.Connection, run_date: str) -> int:
    row = conn.execute(
        "INSERT INTO runs (run_date, status) VALUES (%s, 'running') RETURNING id",
        (run_date,),
    ).fetchone()
    return int(row["id"])


def finish_run(
    conn: psycopg.Connection, run_id: int, *, status: str,
    posts_created: int = 0, detail: str | None = None,
) -> None:
    conn.execute(
        "UPDATE runs SET status = %s, posts_created = %s, detail = %s, "
        "finished_at = now() WHERE id = %s",
        (status, posts_created, detail, run_id),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_runs.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/store/runs.py tests/store/test_runs.py
git commit -m "feat: convert store/runs.py to Postgres dialect"
```

---

### Task 8: Convert `store/jobs.py` to Postgres dialect

**Files:**
- Modify: `claudeshorts/store/jobs.py`
- Test: `tests/store/test_jobs.py`

**Interfaces:**
- Consumes: `db.connect()` (Task 2)
- Produces: unchanged public API — `insert_job`, `save_snapshot`, `get_job`, `recent_jobs`, `max_id`, `mark_running_interrupted`.
- Note for chunk 2: this task migrates the *existing* jobs table structure only. Chunk 2 will extend `status` to the full state machine and add worker-facing columns; nothing here should be read as final job-queue design.

- [ ] **Step 1: Write the failing tests**

```python
# tests/store/test_jobs.py
from __future__ import annotations

from claudeshorts.store import db, jobs


def test_insert_job_and_get_job():
    with db.connect() as conn:
        jobs.insert_job(conn, job_id=1, name="ingest")
        got = jobs.get_job(conn, 1)
        assert got["name"] == "ingest"
        assert got["status"] == "running"


def test_save_snapshot_updates_progress():
    with db.connect() as conn:
        jobs.insert_job(conn, job_id=1, name="ingest")
        jobs.save_snapshot(conn, 1, {
            "status": "ok", "phase_index": 2, "phase_total": 2,
            "phase_label": "done", "progress_current": 10, "progress_total": 10,
            "progress_label": "10/10", "log": "line1\nline2", "error": None,
            "finished_at": "2026-07-10T00:00:00Z",
        })
        got = jobs.get_job(conn, 1)
        assert got["status"] == "ok"
        assert got["progress_current"] == 10


def test_recent_jobs_and_max_id():
    with db.connect() as conn:
        jobs.insert_job(conn, job_id=1, name="a")
        jobs.insert_job(conn, job_id=2, name="b")
        assert jobs.max_id(conn) == 2
        assert [j["id"] for j in jobs.recent_jobs(conn, limit=10)] == [2, 1]


def test_mark_running_interrupted():
    with db.connect() as conn:
        jobs.insert_job(conn, job_id=1, name="a")
        n = jobs.mark_running_interrupted(conn)
        assert n == 1
        assert jobs.get_job(conn, 1)["status"] == "interrupted"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_jobs.py -v`
Expected: FAIL (sqlite `INSERT OR REPLACE`/placeholders invalid against Postgres)

- [ ] **Step 3: Rewrite `claudeshorts/store/jobs.py`**

```python
"""Data-access helpers for the `jobs` table (durable mirror of dashboard jobs).

Background jobs run in memory and stream live (see ``dashboard/jobs.py``); these
helpers persist a snapshot of each so the operator can revisit a job after the
server restarts. The in-memory copy is always the source of truth while a job is
alive; the database is the fallback for history.
"""

from __future__ import annotations

from typing import Any

import psycopg

# The columns a snapshot write touches (everything except id/started_at, which
# are set on insert). Kept in one place so insert + update stay in sync.
_PROGRESS_COLS = (
    "status", "phase_index", "phase_total", "phase_label",
    "progress_current", "progress_total", "progress_label",
    "log", "error", "finished_at",
)


def insert_job(conn: psycopg.Connection, *, job_id: int, name: str) -> None:
    """Record a newly started job. ``job_id`` matches the in-memory job id."""
    conn.execute(
        "INSERT INTO jobs (id, name, status) VALUES (%s, %s, 'running') "
        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = 'running'",
        (job_id, name),
    )


def save_snapshot(conn: psycopg.Connection, job_id: int, snap: dict[str, Any]) -> None:
    """Persist the current state of a job (progress, log, status, finish time)."""
    cols = ", ".join(f"{c} = %s" for c in _PROGRESS_COLS)
    conn.execute(
        f"UPDATE jobs SET {cols} WHERE id = %s",
        tuple(snap.get(c) for c in _PROGRESS_COLS) + (job_id,),
    )


def get_job(conn: psycopg.Connection, job_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    return dict(row) if row else None


def recent_jobs(conn: psycopg.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Most recent jobs, newest first (for the dashboard list)."""
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY id DESC LIMIT %s", (int(limit),)
    ).fetchall()
    return [dict(r) for r in rows]


def max_id(conn: psycopg.Connection) -> int:
    """Largest job id on record, or 0 if the table is empty."""
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM jobs").fetchone()
    return int(row["m"])


def mark_running_interrupted(conn: psycopg.Connection) -> int:
    """Flag jobs left `running` by a dead process as `interrupted`. Startup-only.

    A job only runs inside a live server process; if a row is still `running`
    when the table is read fresh, its thread died with the old process. Returns
    the number of rows updated.
    """
    cur = conn.execute(
        "UPDATE jobs SET status = 'interrupted', finished_at = now() "
        "WHERE status = 'running'"
    )
    return cur.rowcount
```

Note: the old `save_snapshot`/`insert_job`/`mark_running_interrupted` called
`conn.commit()` themselves (Task 8's predecessor ran outside a `with connect()`
block in some dashboard call sites). This rewrite drops the explicit
`conn.commit()` calls — every call site in `dashboard/jobs.py` must be
verified in Step 4 to use `with db.connect() as conn:` so the context manager
commits instead. If any call site holds a connection open across multiple
calls without the `with` block, flag it and add an explicit `conn.commit()`
back rather than assuming this refactor is safe silently.

- [ ] **Step 4: Verify `dashboard/jobs.py` call sites use the context-manager pattern**

Run: `grep -n "insert_job\|save_snapshot\|mark_running_interrupted" claudeshorts/dashboard/jobs.py`

For each call site found, confirm it is inside a `with db.connect() as conn:` (or equivalent) block. If any call site is not, add the missing `with` wrapper in `dashboard/jobs.py` before proceeding — do not skip this check.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/store/test_jobs.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/store/jobs.py tests/store/test_jobs.py
git commit -m "feat: convert store/jobs.py to Postgres dialect"
```

---

### Task 9: Full store-layer integration smoke test against all 8 callers

**Files:**
- Test: `tests/store/test_integration_smoke.py`

**Interfaces:**
- Consumes: all of Tasks 2-8's public APIs.
- Produces: nothing new — a confidence check that the 8 real call sites still import and run against the Postgres-backed store without modification.

- [ ] **Step 1: Write the test**

```python
# tests/store/test_integration_smoke.py
from __future__ import annotations

import importlib


def test_all_caller_modules_import_cleanly():
    """The 8 files that call store/*.py must import without error against the
    new Postgres-backed store (no leftover sqlite3-specific assumptions)."""
    modules = [
        "claudeshorts.dashboard.app",
        "claudeshorts.dashboard.jobs",
        "claudeshorts.generate.runner",
        "claudeshorts.generate.select",
        "claudeshorts.ingest.runner",
        "claudeshorts.orchestrate.runner",
        "claudeshorts.publish.exporter",
        "claudeshorts.review.queue",
    ]
    for name in modules:
        importlib.import_module(name)
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `pytest tests/store/test_integration_smoke.py -v`
Expected: PASS if all imports are clean. If it FAILS, the traceback names the
file and line still assuming sqlite3 — fix that call site directly (it means
Task 3-8's signature preservation missed something) and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/store/test_integration_smoke.py
git commit -m "test: add store-layer caller import smoke test"
```

---

### Task 10: Migration script — copy existing SQLite data into Supabase

**Files:**
- Create: `scripts/migrate_sqlite_to_supabase.py`
- Test: `tests/scripts/test_migrate_sqlite_to_supabase.py`

**Interfaces:**
- Consumes: `claudeshorts.store.db.connect()` (Task 2, Postgres target), a raw `sqlite3.connect(path)` (source, read-only).
- Produces: `main(sqlite_path: Path, *, force: bool = False) -> dict[str, int]` — returns per-table row counts copied; raises `RuntimeError` if the destination is non-empty and `force` is False.

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_migrate_sqlite_to_supabase.py
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from claudeshorts.store import db
from scripts.migrate_sqlite_to_supabase import main


def _make_source_db(tmp_path: Path) -> Path:
    path = tmp_path / "source.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, source TEXT, url TEXT, "
        "title TEXT, summary TEXT, published_at TEXT, content_hash TEXT, "
        "fetched_at TEXT)"
    )
    conn.execute(
        "INSERT INTO items (id, source, url, title, summary, published_at, "
        "content_hash, fetched_at) VALUES "
        "(1, 'test', 'https://a', 'Title', 'sum', NULL, 'hash-1', '2026-01-01')"
    )
    conn.execute(
        "CREATE TABLE posts (id INTEGER PRIMARY KEY, item_ids TEXT, status TEXT, "
        "title TEXT, slides_json TEXT, theme_json TEXT, captions_json TEXT, "
        "review_note TEXT, published_at TEXT, scheduled_for TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE threads (id INTEGER PRIMARY KEY, slug TEXT, title TEXT, "
        "summary TEXT, status TEXT, first_seen TEXT, last_updated TEXT)"
    )
    conn.execute(
        "CREATE TABLE post_threads (post_id INTEGER, thread_id INTEGER)"
    )
    conn.execute(
        "CREATE TABLE pins (item_id INTEGER PRIMARY KEY, note TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY, run_date TEXT, status TEXT, "
        "posts_created INTEGER, detail TEXT, started_at TEXT, finished_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY, name TEXT, status TEXT, "
        "phase_index INTEGER, phase_total INTEGER, phase_label TEXT, "
        "progress_current INTEGER, progress_total INTEGER, progress_label TEXT, "
        "log TEXT, error TEXT, started_at TEXT, finished_at TEXT)"
    )
    conn.commit()
    conn.close()
    return path


def test_migrate_copies_rows_and_verifies_counts(tmp_path):
    source = _make_source_db(tmp_path)
    counts = main(source)
    assert counts["items"] == 1
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM items WHERE id = 1").fetchone()
        assert row["title"] == "Title"


def test_migrate_refuses_nonempty_destination_without_force(tmp_path):
    source = _make_source_db(tmp_path)
    main(source)
    with pytest.raises(RuntimeError, match="non-empty"):
        main(source)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_migrate_sqlite_to_supabase.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.migrate_sqlite_to_supabase'`

- [ ] **Step 3: Implement the migration script**

```python
# scripts/migrate_sqlite_to_supabase.py
"""One-time copy of data/app.db into the Supabase Postgres store.

Usage: python -m scripts.migrate_sqlite_to_supabase [path/to/app.db] [--force]

Reads all rows from the local SQLite file and writes them into the tables
created by claudeshorts.store.db.init_db(), preserving primary key ids so
post_threads foreign keys stay valid. Refuses to run if the destination
already has data, unless --force is passed. Never modifies the source file.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import psycopg

from claudeshorts.store import db

_TABLE_ORDER = ("items", "posts", "threads", "post_threads", "pins", "runs", "jobs")

_SEQUENCE_TABLES = ("items", "posts", "threads", "runs", "jobs")


def _destination_is_empty(conn: psycopg.Connection) -> bool:
    for table in _TABLE_ORDER:
        n = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        if n > 0:
            return False
    return True


def _copy_table(sconn: sqlite3.Connection, pconn: psycopg.Connection, table: str) -> int:
    sconn.row_factory = sqlite3.Row
    rows = sconn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return 0
    columns = rows[0].keys()
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    for row in rows:
        pconn.execute(
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
            tuple(row[c] for c in columns),
        )
    return len(rows)


def _reset_sequences(pconn: psycopg.Connection) -> None:
    for table in _SEQUENCE_TABLES:
        pconn.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
            f"(SELECT MAX(id) FROM {table}) IS NOT NULL)"
        )


def main(sqlite_path: Path, *, force: bool = False) -> dict[str, int]:
    db.init_db()
    counts: dict[str, int] = {}
    with db.connect() as pconn:
        if not force and not _destination_is_empty(pconn):
            raise RuntimeError(
                "Destination Supabase tables are non-empty. Pass --force to "
                "proceed anyway, or truncate the tables first if this is a "
                "deliberate re-run."
            )
        sconn = sqlite3.connect(sqlite_path)
        try:
            for table in _TABLE_ORDER:
                counts[table] = _copy_table(sconn, pconn, table)
            _reset_sequences(pconn)
        finally:
            sconn.close()

    sconn = sqlite3.connect(sqlite_path)
    try:
        for table in _TABLE_ORDER:
            source_n = sconn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if source_n != counts[table]:
                raise RuntimeError(
                    f"Row count mismatch for {table}: source had {source_n}, "
                    f"copied {counts[table]}."
                )
    finally:
        sconn.close()

    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sqlite_path", nargs="?", default="data/app.db", type=Path,
        help="Path to the source SQLite file (default: data/app.db)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Proceed even if the destination tables are non-empty",
    )
    args = parser.parse_args()
    result = main(args.sqlite_path, force=args.force)
    for table, n in result.items():
        print(f"{table}: {n} rows copied")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scripts/test_migrate_sqlite_to_supabase.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_sqlite_to_supabase.py tests/scripts/test_migrate_sqlite_to_supabase.py
git commit -m "feat: add one-time SQLite-to-Supabase migration script"
```

---

### Task 11: Run the real migration against `data/app.db` and verify

**Files:** none created/modified — this is an operational verification step, not code.

- [ ] **Step 1: Back up the source file (belt-and-suspenders; it isn't touched, but confirm)**

Run: `cp data/app.db data/app.db.pre-migration-backup`

- [ ] **Step 2: Run the migration against the real data**

Run: `python -m scripts.migrate_sqlite_to_supabase data/app.db`
Expected output: `items: 616 rows copied`, `posts: 13 rows copied`, `threads: 13 rows copied`, `post_threads: 13 rows copied`, `pins: 0 rows copied`, `runs: 3 rows copied`, `jobs: 1 rows copied` (exact counts may differ slightly if new data was ingested since the design doc was written — that's fine, the script verifies source == destination regardless of the absolute numbers).

- [ ] **Step 3: Spot-check the dashboard against the live Supabase-backed store**

Run: `./start-dashboard.sh` and open the dashboard. Confirm the Posts table, Review queue, and Threads view show the same posts/threads that existed in SQLite before migration.

- [ ] **Step 4: Update `CHECKPOINT_LAST.md` and `TASK_QUEUE.md`**

Move "Chunk 1: Supabase schema + migrate off SQLite" from In-Progress to Done in `TASK_QUEUE.md`, with the verification details from Steps 2-3. Update `CHECKPOINT_LAST.md` with current state and next action (chunk 2: job queue + state machine).

- [ ] **Step 5: Commit the checkpoint updates**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 1 complete — data migrated to Supabase, verified live"
```

---

## Self-Review Notes

**Spec coverage:** DB access approach (psycopg3 raw SQL, Session Pooler) → Task 2. Schema mapping table → Task 2's `SCHEMA`. Migration script with dependency-ordered copy, ID preservation, sequence reset, row-count verification, non-empty guard → Task 10. Secrets (`SUPABASE_DB_URL` in `.env.example`) → Task 1. RPi fail-fast connection behavior (`connect_timeout`, keepalives) → Task 2. Testing against a real Postgres target → Tasks 2-9 (all use the live Supabase project created during brainstorming; a local Docker Postgres was considered in the spec but the live project is simpler to wire up now and costs $0, so tests target it directly via `tests/store/conftest.py`'s truncate-between-tests fixture). Out-of-scope items (job state machine, service layer, storage-provider plugin registry) are explicitly deferred to their own chunks.

**Type consistency:** `dict_row` factory established in Task 2 is relied on by every later task's `dict(row)` / `row["col"]` access — verified consistent across items/posts/threads/pins/runs/jobs. `RETURNING id` + `.fetchone()["id"]` pattern used consistently everywhere a `lastrowid` used to be read (posts, threads, runs). JSONB round-tripping (`Jsonb(...)` wrapper on write, plain dict on read) used only in `posts.py`, matching the schema's JSONB columns from Task 2.
