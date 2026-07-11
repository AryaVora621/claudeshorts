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
# profiles:     multi-profile scope for independent content pipelines
SCHEMA = """
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
    layout        TEXT        DEFAULT 'slideshow',
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
    status           TEXT        NOT NULL DEFAULT 'PENDING',
    job_type         TEXT        NOT NULL DEFAULT 'legacy',
    payload          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    attempts         INTEGER     NOT NULL DEFAULT 0,
    max_attempts     INTEGER     NOT NULL DEFAULT 3,
    next_attempt_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancel_requested BOOLEAN     NOT NULL DEFAULT false,
    pause_requested  BOOLEAN     NOT NULL DEFAULT false,
    locked_by        TEXT,
    locked_at        TIMESTAMPTZ,
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

-- Upgrade pre-chunk-2 databases in place with ADD COLUMN IF NOT EXISTS.
-- Existing posts get layout set to slideshow (default).
ALTER TABLE posts ADD COLUMN IF NOT EXISTS layout TEXT DEFAULT 'slideshow';

-- Upgrade pre-chunk-2 databases in place with ADD COLUMN IF NOT EXISTS.
-- Existing jobs keep their old status values (lowercase); Task 8 dashboard
-- must handle both vocabularies for historical display.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS job_type TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 3;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS pause_requested BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS locked_by TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ;
ALTER TABLE jobs ALTER COLUMN status SET DEFAULT 'PENDING';

CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs(status, next_attempt_at);

CREATE TABLE IF NOT EXISTS schedules (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT        NOT NULL UNIQUE,
    job_type        TEXT        NOT NULL,
    payload         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    kind            TEXT        NOT NULL,
    daily_at        TEXT,
    every_minutes   INTEGER,
    weekday         INTEGER,
    enabled         BOOLEAN     NOT NULL DEFAULT true,
    next_run_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_run_job_id BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Multi-profile reshape: scope items/posts/threads/runs/schedules to a
-- profile. NULL profile_id on legacy rows is resolved by
-- scripts/migrate_profiles_backfill.py (Task 5), not by this schema.
ALTER TABLE items     ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE posts     ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE threads   ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE runs      ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE schedules ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);

DROP INDEX IF EXISTS idx_items_content_hash;
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_content_hash
    ON items(content_hash) WHERE profile_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_items_content_hash_profile
    ON items(profile_id, content_hash);

CREATE INDEX IF NOT EXISTS idx_posts_profile_status ON posts(profile_id, status);
CREATE INDEX IF NOT EXISTS idx_runs_profile_date ON runs(profile_id, run_date);
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
