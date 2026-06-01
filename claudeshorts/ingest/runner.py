"""Ingestion runner: fetch every configured source, filter by age, dedupe, store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import settings
from ..config import sources as load_sources
from ..store import connect
from ..store.items import count_items, insert_item
from .fetchers import fetch_source


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _cutoff(since: str | None, max_age_hours: int | None) -> datetime | None:
    if since:
        return _parse_iso(since)
    if max_age_hours:
        return datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return None


def _is_recent(published_at: str | None, cutoff: datetime | None) -> bool:
    # Keep items with no date (we can't prove they're stale).
    if cutoff is None or not published_at:
        return True
    try:
        return _parse_iso(published_at) >= cutoff
    except ValueError:
        return True


def run_ingest(since: str | None = None, limit: int | None = None) -> dict[str, Any]:
    """Fetch all sources and store fresh, non-duplicate items.

    Returns a stats dict (fetched / stored / duplicates / skipped_old, plus a
    per-source breakdown and the resulting total item count).
    """
    cfg = settings().get("ingest", {})
    max_age = cfg.get("max_age_hours", 48)
    per_source = limit or cfg.get("per_source_limit", 25)
    cutoff = _cutoff(since, max_age)

    stats: dict[str, Any] = {
        "fetched": 0, "stored": 0, "duplicates": 0, "skipped_old": 0,
        "by_source": {},
    }

    with connect() as conn:
        for source in load_sources():
            name = source.get("name", "?")
            per = {"fetched": 0, "stored": 0}
            try:
                items = fetch_source(source, per_source)
            except Exception as exc:  # one bad source shouldn't kill the run
                stats["by_source"][name] = {"error": str(exc)}
                continue
            for item in items:
                stats["fetched"] += 1
                per["fetched"] += 1
                if not _is_recent(item["published_at"], cutoff):
                    stats["skipped_old"] += 1
                    continue
                if insert_item(conn, item):
                    stats["stored"] += 1
                    per["stored"] += 1
                else:
                    stats["duplicates"] += 1
            stats["by_source"][name] = per
        conn.commit()
        stats["total_items"] = count_items(conn)

    return stats
