from __future__ import annotations

from claudeshorts.services import articles_service
from claudeshorts.store import connect
from claudeshorts.store.pins import is_pinned


def test_add_manual_article_pins_by_default():
    result = articles_service.add_manual_article(title="Hello World")
    assert result["created"] is True
    with connect() as conn:
        assert is_pinned(conn, result["item_id"]) is True
    assert "job_id" not in result


def test_add_manual_article_generate_action_enqueues_job():
    result = articles_service.add_manual_article(
        title="Hello Again", action="generate"
    )
    assert "job_id" in result
    with connect() as conn:
        assert is_pinned(conn, result["item_id"]) is False


def test_pin_and_unpin_article():
    result = articles_service.add_manual_article(title="Pin Me", action="pin")
    item_id = result["item_id"]
    articles_service.unpin_article(item_id)
    with connect() as conn:
        assert is_pinned(conn, item_id) is False
    articles_service.pin_article(item_id)
    with connect() as conn:
        assert is_pinned(conn, item_id) is True


def test_generate_from_item_enqueues_job():
    result = articles_service.add_manual_article(title="Gen Me", action="pin")
    out = articles_service.generate_from_item(result["item_id"])
    assert isinstance(out["job_id"], int)
