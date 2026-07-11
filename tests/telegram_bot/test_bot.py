from __future__ import annotations

from unittest.mock import MagicMock

from claudeshorts.telegram_bot.bot import format_queue, format_job, is_authorized


def test_format_queue_lists_titles_and_ids():
    posts = [{"id": 1, "title": "GPT-5.5 ships"}, {"id": 2, "title": "Nvidia earnings"}]
    text = format_queue(posts)
    assert "1" in text and "GPT-5.5 ships" in text
    assert "2" in text and "Nvidia earnings" in text


def test_format_queue_empty():
    assert "no posts" in format_queue([]).lower()


def test_format_job_includes_status_and_id():
    job = {"id": 9, "status": "failed", "job_type": "generate", "attempts": 3, "error": "boom"}
    text = format_job(job)
    assert "9" in text and "failed" in text and "boom" in text


def test_is_authorized_matches_configured_chat_id():
    assert is_authorized(chat_id=555, allowed_chat_id=555) is True
    assert is_authorized(chat_id=1, allowed_chat_id=555) is False
