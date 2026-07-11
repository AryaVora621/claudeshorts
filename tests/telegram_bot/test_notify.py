from __future__ import annotations

from unittest.mock import patch

from claudeshorts.telegram_bot import notify


def test_send_notification_posts_to_telegram_api(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "555")
    with patch("claudeshorts.telegram_bot.notify.httpx.post") as mock_post:
        notify.send_notification("job done")
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.telegram.org/bottest-token/sendMessage"
    assert kwargs["json"] == {"chat_id": "555", "text": "job done"}


def test_send_notification_noop_without_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with patch("claudeshorts.telegram_bot.notify.httpx.post") as mock_post:
        notify.send_notification("job done")
    mock_post.assert_not_called()


def test_send_notification_swallows_network_errors(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "555")
    with patch("claudeshorts.telegram_bot.notify.httpx.post", side_effect=RuntimeError("boom")):
        notify.send_notification("job done")  # must not raise


def test_send_notification_truncates_long_text(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "555")
    with patch("claudeshorts.telegram_bot.notify.httpx.post") as mock_post:
        notify.send_notification("x" * 5000)
    assert len(mock_post.call_args.kwargs["json"]["text"]) == 4000
