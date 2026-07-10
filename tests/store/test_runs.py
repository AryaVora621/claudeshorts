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
