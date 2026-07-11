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
