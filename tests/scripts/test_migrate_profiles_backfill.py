from __future__ import annotations

from claudeshorts.store import db
from scripts.migrate_profiles_backfill import backfill_profiles


def test_backfill_assigns_legacy_rows_to_fork_ai():
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO items (source, url, title, content_hash) "
            "VALUES ('hn', 'https://x', 'X', 'legacy-hash')"
        )
        conn.execute(
            "INSERT INTO posts (title, status) VALUES ('Legacy Post', 'draft')"
        )
        conn.commit()

        counts = backfill_profiles(conn)

        fork_ai_id = conn.execute(
            "SELECT id FROM profiles WHERE slug = 'fork-ai'"
        ).fetchone()["id"]
        remaining_null_items = conn.execute(
            "SELECT COUNT(*) AS n FROM items WHERE profile_id IS NULL"
        ).fetchone()["n"]
        remaining_null_posts = conn.execute(
            "SELECT COUNT(*) AS n FROM posts WHERE profile_id IS NULL"
        ).fetchone()["n"]

        assert remaining_null_items == 0
        assert remaining_null_posts == 0
        assert counts["items"] >= 1
        assert counts["posts"] >= 1

        item_profile = conn.execute(
            "SELECT profile_id FROM items WHERE content_hash = 'legacy-hash'"
        ).fetchone()["profile_id"]
        assert item_profile == fork_ai_id


def test_backfill_is_idempotent():
    with db.connect() as conn:
        backfill_profiles(conn)
        counts_second_run = backfill_profiles(conn)
        assert counts_second_run == {
            "items": 0, "posts": 0, "threads": 0, "runs": 0, "schedules": 0,
        }
