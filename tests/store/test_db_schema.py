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
