"""Internal pipeline performance reporting. Real cross-platform engagement
(views/likes/follows) is out of scope until chunk 11 wires up Playwright-
based analytics scraping via logged-in browser profiles — the
`platform_engagement` field is a placeholder so the report's shape doesn't
need to change once that data exists.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..store import connect
from ..store.posts import recent_posts, status_counts
from ..store.runs import recent_runs


def weekly_report(as_of: date | None = None) -> dict[str, Any]:
    as_of = as_of or date.today()
    week_start = as_of - timedelta(days=as_of.weekday())
    week_end = week_start + timedelta(days=6)

    with connect() as conn:
        posts_this_week = recent_posts(conn, days=7)
        counts = status_counts(conn)
        runs = recent_runs(conn, limit=10)

    by_status: dict[str, int] = {}
    exports_by_platform: dict[str, int] = {}
    for p in posts_this_week:
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1

    ok_runs = sum(1 for r in runs if r["status"] == "ok")
    error_runs = sum(1 for r in runs if r["status"] == "error")

    return {
        "week_start": week_start.isoformat(), "week_end": week_end.isoformat(),
        "posts_generated": len(posts_this_week),
        "posts_approved": by_status.get("approved", 0) + by_status.get("exported", 0),
        "posts_rejected": by_status.get("rejected", 0),
        "posts_exported": by_status.get("exported", 0),
        "exports_by_platform": exports_by_platform,
        "ingest_runs": {"ok": ok_runs, "error": error_runs},
        "platform_engagement": {
            "status": "pending",
            "note": (
                "Requires Playwright-based analytics scraping via logged-in "
                "browser profiles — see chunk 11."
            ),
        },
    }
