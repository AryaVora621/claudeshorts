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
