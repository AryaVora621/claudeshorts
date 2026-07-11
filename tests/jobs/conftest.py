from __future__ import annotations

import pytest

from claudeshorts.store import db

_TABLES = ("post_threads", "pins", "jobs", "runs", "posts", "threads", "items", "schedules")


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate all tables before each test so tests are independent."""
    db.init_db()
    with db.connect() as conn:
        for t in _TABLES:
            conn.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE")
    yield


@pytest.fixture(autouse=True)
def _no_live_telegram_notifications(monkeypatch):
    """Job tests exercise real failure/completion paths that call
    send_notification; a real TELEGRAM_BOT_TOKEN/CHAT_ID in the environment
    (e.g. loaded from .env by another test module) must never turn a test
    run into a live message to the admin chat."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
