"""Per-source fetchers that return normalized news items.

Each source in config/sources.yaml has a ``kind`` (rss | hackernews | reddit).
``fetch_source`` dispatches to the matching fetcher and every fetcher returns a
list of dicts shaped for the ``items`` table, including a stable content hash
used for dedupe.

To stay ToS-safe we only keep titles, short summaries, and links — no
paywalled full-text scraping.
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

USER_AGENT = "claudeshorts/0.1 (news aggregator)"
_TIMEOUT = httpx.Timeout(20.0)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# --- helpers ---------------------------------------------------------------
def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip().lower())


def content_hash(url: str | None, title: str | None) -> str:
    """Stable dedupe key from normalized url + title."""
    base = f"{_normalize(url or '')}|{_normalize(title or '')}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _clean_summary(text: str | None, limit: int = 600) -> str | None:
    if not text:
        return None
    stripped = html.unescape(_TAG_RE.sub("", text)).strip()
    stripped = _WS_RE.sub(" ", stripped)
    if not stripped:
        return None
    return stripped[:limit]


def _item(source: dict, title: str, url: str | None, summary: str | None,
          published_at: str | None) -> dict[str, Any]:
    return {
        "source": source["name"],
        "url": url,
        "title": title.strip(),
        "summary": summary,
        "published_at": published_at,
        "content_hash": content_hash(url, title),
    }


def _struct_to_iso(struct_time) -> str | None:
    if not struct_time:
        return None
    try:
        return datetime(*struct_time[:6], tzinfo=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _get_json(url: str, params: dict[str, Any]) -> dict:
    resp = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT},
                     timeout=_TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


# --- fetchers --------------------------------------------------------------
def _fetch_rss(source: dict, limit: int) -> list[dict]:
    # Pass our UA: some feeds reject feedparser's default agent.
    feed = feedparser.parse(source["url"], agent=USER_AGENT)
    items: list[dict] = []
    for entry in feed.entries[:limit]:
        title = entry.get("title", "").strip()
        if not title:
            continue
        published = _struct_to_iso(
            entry.get("published_parsed") or entry.get("updated_parsed")
        )
        items.append(_item(
            source, title, entry.get("link"),
            _clean_summary(entry.get("summary")), published,
        ))
    return items


def _fetch_hackernews(source: dict, limit: int) -> list[dict]:
    query = source.get("query", "") or ""
    params: dict[str, Any] = {
        "tags": "story" if query else "front_page",
        "hitsPerPage": limit,
    }
    if query:
        params["query"] = query
    data = _get_json("https://hn.algolia.com/api/v1/search", params)
    items: list[dict] = []
    for hit in data.get("hits", []):
        title = (hit.get("title") or hit.get("story_title") or "").strip()
        if not title:
            continue
        link = hit.get("url") or hit.get("story_url") or (
            f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        )
        items.append(_item(source, title, link, None, hit.get("created_at")))
    return items


def _fetch_reddit(source: dict, limit: int) -> list[dict]:
    sub = source["subreddit"]
    data = _get_json(
        f"https://www.reddit.com/r/{sub}/hot.json",
        {"limit": limit, "raw_json": 1},
    )
    items: list[dict] = []
    for child in data.get("data", {}).get("children", []):
        d = child.get("data", {})
        if d.get("stickied"):
            continue
        title = (d.get("title") or "").strip()
        if not title:
            continue
        link = d.get("url_overridden_by_dest") or (
            "https://www.reddit.com" + d.get("permalink", "")
        )
        created = d.get("created_utc")
        published = (
            datetime.fromtimestamp(created, tz=timezone.utc).isoformat()
            if created else None
        )
        items.append(_item(
            source, title, link, _clean_summary(d.get("selftext")), published,
        ))
    return items


_FETCHERS = {
    "rss": _fetch_rss,
    "hackernews": _fetch_hackernews,
    "reddit": _fetch_reddit,
}


def fetch_source(source: dict, limit: int) -> list[dict]:
    """Fetch + normalize one configured source. Raises on unknown kind."""
    kind = source.get("kind")
    fetcher = _FETCHERS.get(kind)
    if fetcher is None:
        raise ValueError(f"unknown source kind: {kind!r} (source {source.get('name')})")
    return fetcher(source, limit)
