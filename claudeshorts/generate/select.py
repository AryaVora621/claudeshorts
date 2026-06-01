"""Topic selection: rank fresh items, dedupe vs recent posts, detect follow-ups.

Consults content memory first (used items + open threads) so we never repeat a
covered item and so items that advance an existing storyline are flagged as
follow-ups for the generator to build on.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..config import settings
from ..config import sources as load_sources
from ..store import connect
from ..store.items import recent_items
from ..store.posts import used_item_ids
from ..store.threads import open_threads

# Small stopword set so token overlap reflects topical, not grammatical, words.
_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "have", "will",
    "your", "about", "into", "after", "over", "more", "than", "what",
    "when", "where", "which", "who", "how", "new", "now", "says", "said",
    "could", "would", "should", "they", "their", "them", "its", "are",
    "was", "were", "has", "had", "but", "not", "you", "all", "can",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Follow-up if an item shares this many topical tokens with an open thread.
_FOLLOWUP_MIN_OVERLAP = 2
# Skip a candidate if it nearly duplicates an already-selected item.
_DUP_MIN_OVERLAP = 4


def _tokens(text: str | None) -> set[str]:
    return {
        t for t in _TOKEN_RE.findall((text or "").lower())
        if len(t) > 3 and t not in _STOPWORDS
    }


def _source_weights() -> dict[str, float]:
    return {s["name"]: float(s.get("weight", 1.0)) for s in load_sources()}


def _recency_bonus(item: dict, window_days: int) -> float:
    """0..1 bonus, higher for newer items (by published_at, else fetched_at)."""
    stamp = item.get("published_at") or item.get("fetched_at")
    if not stamp:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    window_h = max(window_days * 24, 1)
    return max(0.0, 1.0 - age_h / window_h)


def _match_thread(item: dict, threads: list[dict]) -> dict | None:
    item_tokens = _tokens(item["title"]) | _tokens(item.get("summary"))
    best: dict | None = None
    best_overlap = 0
    for th in threads:
        overlap = len(item_tokens & (_tokens(th["title"]) | _tokens(th.get("summary"))))
        if overlap > best_overlap:
            best, best_overlap = th, overlap
    return best if best_overlap >= _FOLLOWUP_MIN_OVERLAP else None


def select_topics(
    limit: int | None = None, lookback_days: int | None = None,
) -> list[dict[str, Any]]:
    """Pick up to `limit` topics. Each result is:
    ``{item, score, weight, follow_up_thread}``.
    """
    cfg = settings()
    limit = limit or cfg.get("posts_per_day", 3)
    lookback = lookback_days or cfg.get("select", {}).get("lookback_days", 14)
    weights = _source_weights()

    with connect() as conn:
        used = used_item_ids(conn, lookback)
        candidates = [it for it in recent_items(conn, lookback) if it["id"] not in used]
        threads = open_threads(conn)

    scored: list[tuple[float, dict]] = []
    for it in candidates:
        weight = weights.get(it["source"], 1.0)
        score = weight + _recency_bonus(it, lookback)
        scored.append((score, it))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    selected: list[dict[str, Any]] = []
    picked_tokens: list[set[str]] = []
    for score, it in scored:
        toks = _tokens(it["title"])
        if any(len(toks & prev) >= _DUP_MIN_OVERLAP for prev in picked_tokens):
            continue  # too similar to something already chosen this run
        selected.append({
            "item": it,
            "score": round(score, 3),
            "weight": weights.get(it["source"], 1.0),
            "follow_up_thread": _match_thread(it, threads),
        })
        picked_tokens.append(toks)
        if len(selected) >= limit:
            break
    return selected
