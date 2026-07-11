"""Push notifications — separate from bot.py's pull-based commands.

Fire-and-forget: a notification failure must never break the job/
scheduler pipeline that triggered it, so exceptions are logged, not
raised.
"""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)


def send_notification(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000]},
            timeout=10,
        )
    except Exception as exc:
        log.warning("Telegram notification failed: %s", exc)
