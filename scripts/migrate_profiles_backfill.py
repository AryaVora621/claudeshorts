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
