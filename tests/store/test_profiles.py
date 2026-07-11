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
