"""SQLite schema definition and connection helpers.

The schema is intentionally small and additive. `init_db()` is idempotent
(``CREATE TABLE IF NOT EXISTS``), so it is safe to call on every startup.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..config import DB_PATH, ensure_dirs

# --- Schema ----------------------------------------------------------------
# items:        raw normalized news items from ingestion (Phase 1)
# posts:        a generated piece of content + its lifecycle status (Phase 2+)
# threads:      an ongoing storyline that posts attach to (content memory)
# post_threads: many-to-many link between posts and threads
SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT    NOT NULL,
    url           TEXT,
    title         TEXT    NOT NULL,
    summary       TEXT,
    published_at  TEXT,
    content_hash  TEXT    NOT NULL,
    fetched_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
-- `seen` dedupe index: never store the same item twice.
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_content_hash ON items(content_hash);
CREATE INDEX IF NOT EXISTS idx_items_published_at ON items(published_at);

CREATE TABLE IF NOT EXISTS posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_ids      TEXT,                       -- JSON array of items.id
    status        TEXT    NOT NULL DEFAULT 'draft',
                                              -- draft|rendered|approved|rejected|exported
    title         TEXT,
    slides_json   TEXT,                       -- JSON: structured slide content
    theme_json    TEXT,                       -- JSON: per-post color theme
    captions_json TEXT,                       -- JSON: per-platform captions/hashtags
    review_note   TEXT,
    published_at  TEXT,                       -- stamped on export (content memory)
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);

CREATE TABLE IF NOT EXISTS threads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT    NOT NULL UNIQUE,
    title         TEXT    NOT NULL,
    summary       TEXT,
    status        TEXT    NOT NULL DEFAULT 'ongoing',   -- ongoing|dormant
    first_seen    TEXT    NOT NULL DEFAULT (datetime('now')),
    last_updated  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS post_threads (
    post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    thread_id  INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, thread_id)
);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date      TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'running',   -- running|ok|error
    posts_created INTEGER NOT NULL DEFAULT 0,
    detail        TEXT,
    started_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(run_date);

-- pins: items the operator manually flagged (via the dashboard) to be turned
-- into a post. Selection force-includes these ahead of the auto-ranked
-- candidates; the pin is cleared once a post is generated from the item.
CREATE TABLE IF NOT EXISTS pins (
    item_id    INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    note       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a connection with sensible defaults (row factory + foreign keys)."""
    ensure_dirs()
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added after initial release: (table, column, definition). Applied as
# additive ALTERs so existing databases pick them up without a rebuild.
_MIGRATIONS = [
    ("posts", "theme_json", "TEXT"),
    # scheduled_for: optional target publish date (YYYY-MM-DD) for the future-
    # posts queue. NULL = publish on approval; set = held until that date.
    ("posts", "scheduled_for", "TEXT"),
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for table, column, decl in _MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db(db_path: Path | None = None) -> Path:
    """Create the schema if needed. Idempotent. Returns the db path used."""
    path = db_path or DB_PATH
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        _apply_migrations(conn)
        conn.commit()
    return path
