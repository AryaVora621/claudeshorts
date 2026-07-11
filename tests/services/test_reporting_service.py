from __future__ import annotations

from datetime import date

from claudeshorts.services import reporting_service
from claudeshorts.store import connect, posts


def _mk(status="draft", **overrides):
    kwargs = dict(item_ids=[1], title="T", slides={}, captions={}, status=status)
    kwargs.update(overrides)
    with connect() as conn:
        return posts.insert_post(conn, **kwargs)


def test_weekly_report_counts_posts_by_status():
    _mk(status="draft")
    _mk(status="approved")
    _mk(status="rejected")
    report = reporting_service.weekly_report(as_of=date(2026, 7, 10))
    assert report["posts_generated"] == 3
    assert report["posts_approved"] == 1
    assert report["posts_rejected"] == 1


def test_weekly_report_has_pending_engagement_placeholder():
    report = reporting_service.weekly_report(as_of=date(2026, 7, 10))
    assert report["platform_engagement"]["status"] == "pending"
