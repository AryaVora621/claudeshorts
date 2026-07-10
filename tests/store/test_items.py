from __future__ import annotations

from claudeshorts.store import db, items


def test_insert_item_then_dedupe():
    with db.connect() as conn:
        item = {
            "source": "test", "url": "https://a", "title": "Title A",
            "summary": "sum", "published_at": None, "content_hash": "hash-a",
        }
        assert items.insert_item(conn, item) is True
        assert items.insert_item(conn, item) is False
        assert items.count_items(conn) == 1


def test_get_item_and_latest_items():
    with db.connect() as conn:
        items.insert_item(conn, {
            "source": "test", "url": None, "title": "T1", "summary": None,
            "published_at": None, "content_hash": "h1",
        })
        row_id = conn.execute("SELECT id FROM items WHERE content_hash = 'h1'").fetchone()["id"]
        got = items.get_item(conn, row_id)
        assert got["title"] == "T1"
        latest = items.latest_items(conn, limit=10)
        assert len(latest) == 1


def test_get_items_preserves_order():
    with db.connect() as conn:
        ids = []
        for h in ("h1", "h2", "h3"):
            items.insert_item(conn, {
                "source": "test", "url": None, "title": h, "summary": None,
                "published_at": None, "content_hash": h,
            })
            ids.append(conn.execute(
                "SELECT id FROM items WHERE content_hash = %s", (h,)
            ).fetchone()["id"])
        fetched = items.get_items(conn, [ids[2], ids[0]])
        assert [r["id"] for r in fetched] == [ids[2], ids[0]]


def test_insert_manual_item_idempotent_by_content():
    with db.connect() as conn:
        id1, created1 = items.insert_manual_item(conn, title="Hello", url="https://x")
        id2, created2 = items.insert_manual_item(conn, title="Hello", url="https://x")
        assert created1 is True
        assert created2 is False
        assert id1 == id2


def test_recent_items_filters_by_days():
    with db.connect() as conn:
        items.insert_item(conn, {
            "source": "test", "url": None, "title": "Recent", "summary": None,
            "published_at": None, "content_hash": "recent-1",
        })
        recent = items.recent_items(conn, days=1)
        assert len(recent) == 1
        assert recent[0]["title"] == "Recent"
