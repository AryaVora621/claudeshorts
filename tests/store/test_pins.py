from __future__ import annotations

from claudeshorts.store import db, items, pins


def _mk_item(conn, content_hash):
    items.insert_item(conn, {
        "source": "test", "url": None, "title": "T", "summary": None,
        "published_at": None, "content_hash": content_hash,
    })
    return conn.execute(
        "SELECT id FROM items WHERE content_hash = %s", (content_hash,)
    ).fetchone()["id"]


def test_pin_unpin_and_is_pinned():
    with db.connect() as conn:
        item_id = _mk_item(conn, "h1")
        assert pins.is_pinned(conn, item_id) is False
        pins.pin_item(conn, item_id, note="check this out")
        assert pins.is_pinned(conn, item_id) is True
        pins.unpin_item(conn, item_id)
        assert pins.is_pinned(conn, item_id) is False


def test_pin_item_upserts_note():
    with db.connect() as conn:
        item_id = _mk_item(conn, "h1")
        pins.pin_item(conn, item_id, note="first")
        pins.pin_item(conn, item_id, note="second")
        assert pins.pinned_items(conn)[0]["pin_note"] == "second"


def test_pinned_item_ids_and_pinned_items_order():
    with db.connect() as conn:
        id1 = _mk_item(conn, "h1")
        id2 = _mk_item(conn, "h2")
        pins.pin_item(conn, id1)
        pins.pin_item(conn, id2)
        assert pins.pinned_item_ids(conn) == [id1, id2]
        assert [r["id"] for r in pins.pinned_items(conn)] == [id1, id2]
