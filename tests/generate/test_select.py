from __future__ import annotations

import pytest

from claudeshorts.generate.select import select_topics
from claudeshorts.store import connect
from claudeshorts.store.items import insert_item
from claudeshorts.store.profiles import upsert_profile


def _fake_sources(calls, name="hn", weight=1.0):
    def _load(slug):
        calls.append(slug)
        return [{"name": name, "weight": weight}]
    return _load


def test_select_topics_uses_profile_specific_sources(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        "claudeshorts.generate.select.load_profile_sources",
        _fake_sources(calls),
    )
    with connect() as conn:
        profile_id = upsert_profile(conn, slug="fork-ai", display_name="fork.ai")
        insert_item(
            conn,
            {
                "source": "hn", "url": "http://x", "title": "GPT-5 launches today",
                "summary": "big news", "published_at": None, "content_hash": "h1",
            },
            profile_id,
        )
        conn.commit()

    topics = select_topics(profile_id, limit=5)

    assert calls == ["fork-ai"]
    assert len(topics) == 1
    assert topics[0]["item"]["title"] == "GPT-5 launches today"


def test_select_topics_raises_for_unknown_profile():
    with pytest.raises(ValueError, match="no profile"):
        select_topics(999999, limit=5)


def test_select_topics_scopes_items_to_profile(monkeypatch):
    monkeypatch.setattr(
        "claudeshorts.generate.select.load_profile_sources",
        lambda slug: [{"name": "hn", "weight": 1.0}],
    )
    with connect() as conn:
        p1 = upsert_profile(conn, slug="fork-ai", display_name="fork.ai")
        p2 = upsert_profile(conn, slug="midnight-curiosity", display_name="Midnight Curiosity")
        insert_item(
            conn,
            {
                "source": "hn", "url": "http://a", "title": "Item for profile one",
                "summary": "", "published_at": None, "content_hash": "ha",
            },
            p1,
        )
        insert_item(
            conn,
            {
                "source": "hn", "url": "http://b", "title": "Item for profile two",
                "summary": "", "published_at": None, "content_hash": "hb",
            },
            p2,
        )
        conn.commit()

    topics_p1 = select_topics(p1, limit=5)
    titles = {t["item"]["title"] for t in topics_p1}
    assert titles == {"Item for profile one"}
