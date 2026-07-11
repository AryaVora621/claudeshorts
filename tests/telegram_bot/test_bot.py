from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from claudeshorts.telegram_bot.bot import build_application, format_queue, format_job, is_authorized

ALLOWED_CHAT_ID = 555


def _handlers(client):
    """Real registered command callbacks, keyed by command name, from a real
    Application built with a fake ApiClient — exercises the actual guard +
    dispatch wiring, not just the pure formatting helpers."""
    app = build_application("123:fake-token", ALLOWED_CHAT_ID, client)
    out = {}
    for group in app.handlers.values():
        for h in group:
            for command in h.commands:
                out[command] = h.callback
    return out


def _update(chat_id, args=None):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = args or []
    return update, context


def test_unauthorized_chat_is_rejected_without_calling_client():
    client = MagicMock()
    handlers = _handlers(client)
    update, context = _update(chat_id=999)
    asyncio.run(handlers["queue"](update, context))
    update.message.reply_text.assert_awaited_once_with("Not authorized.")
    client.list_posts.assert_not_called()


def test_queue_cmd_calls_list_posts_and_formats_reply():
    client = MagicMock()
    client.list_posts.return_value = [{"id": 1, "title": "GPT-5.5 ships"}]
    handlers = _handlers(client)
    update, context = _update(chat_id=ALLOWED_CHAT_ID)
    asyncio.run(handlers["queue"](update, context))
    client.list_posts.assert_called_once_with(status="rendered")
    update.message.reply_text.assert_awaited_once_with(format_queue(client.list_posts.return_value))


def test_generate_cmd_calls_generate_with_parsed_count():
    client = MagicMock()
    client.generate.return_value = {"job_id": 7}
    handlers = _handlers(client)
    update, context = _update(chat_id=ALLOWED_CHAT_ID, args=["3"])
    asyncio.run(handlers["generate"](update, context))
    client.generate.assert_called_once_with(3)
    update.message.reply_text.assert_awaited_once_with("Enqueued job #7")


def test_approve_cmd_calls_approve_with_parsed_id():
    client = MagicMock()
    client.approve.return_value = {"exported": True}
    handlers = _handlers(client)
    update, context = _update(chat_id=ALLOWED_CHAT_ID, args=["9"])
    asyncio.run(handlers["approve"](update, context))
    client.approve.assert_called_once_with(9)


def test_reject_cmd_calls_reject_with_parsed_id_and_note():
    client = MagicMock()
    handlers = _handlers(client)
    update, context = _update(chat_id=ALLOWED_CHAT_ID, args=["9", "bad", "take"])
    asyncio.run(handlers["reject"](update, context))
    client.reject.assert_called_once_with(9, note="bad take")


def test_retry_cmd_calls_retry_job_with_parsed_id():
    client = MagicMock()
    client.retry_job.return_value = {"job_id": 10}
    handlers = _handlers(client)
    update, context = _update(chat_id=ALLOWED_CHAT_ID, args=["9"])
    asyncio.run(handlers["retry"](update, context))
    client.retry_job.assert_called_once_with(9)
    update.message.reply_text.assert_awaited_once_with("Retried as job #10")


def test_profiles_cmd_calls_list_profiles():
    client = MagicMock()
    client.list_profiles.return_value = []
    handlers = _handlers(client)
    update, context = _update(chat_id=ALLOWED_CHAT_ID)
    asyncio.run(handlers["profiles"](update, context))
    client.list_profiles.assert_called_once_with()
    update.message.reply_text.assert_awaited_once_with("No profiles configured yet.")


def test_workers_cmd_calls_list_jobs_running():
    client = MagicMock()
    client.list_jobs.return_value = []
    handlers = _handlers(client)
    update, context = _update(chat_id=ALLOWED_CHAT_ID)
    asyncio.run(handlers["workers"](update, context))
    client.list_jobs.assert_called_once_with(status="running")


def test_logs_cmd_calls_get_job_with_parsed_id():
    client = MagicMock()
    client.get_job.return_value = {
        "id": 9, "job_type": "generate", "status": "failed", "attempts": 1, "log": "trace",
    }
    handlers = _handlers(client)
    update, context = _update(chat_id=ALLOWED_CHAT_ID, args=["9"])
    asyncio.run(handlers["logs"](update, context))
    client.get_job.assert_called_once_with(9)


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
