from __future__ import annotations

import pytest

from claudeshorts.store import db

_TABLES = (
	"post_threads", "pins", "jobs", "runs", "posts", "threads", "items",
	"schedules", "profiles",
)


@pytest.fixture(autouse=True)
def _clean_tables():
	"""Truncate all tables before each test so tests are independent.

	Issued as a single multi-table TRUNCATE rather than one statement per
	table: separate TRUNCATE ... CASCADE statements against a remote,
	pooled Postgres (Supabase) can each pull in overlapping FK-linked
	tables (now that "profiles" cascades into items/posts/threads/runs/
	jobs/post_threads too) and race with the previous test's connection
	teardown, producing spurious `DeadlockDetected` errors. A single
	TRUNCATE of all tables together acquires every lock in one atomic
	statement, which Postgres cannot deadlock against itself.
	"""
	db.init_db()
	with db.connect() as conn:
		conn.execute(f"TRUNCATE TABLE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")
	yield


@pytest.fixture
def db_conn():
	"""A single open connection for tests that need to read/write directly
	(e.g. seeding profiles, then asserting on rows the scheduler wrote)."""
	with db.connect() as conn:
		yield conn
