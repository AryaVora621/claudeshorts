"""Data-access helpers for the profiles table (multi-brand content profiles,
e.g. fork.ai, Midnight Curiosity).

upsert_profile is safe to call on every boot (re-seeding from
config/profiles/<slug>/profile.yaml) because the ON CONFLICT arm never
touches auto_publish or active — those are operator-toggled at runtime,
mirroring how scheduling/store.py::upsert_schedule protects next_run_at.
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
