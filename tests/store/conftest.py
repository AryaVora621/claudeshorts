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

    Seeds two profiles (ids 1 and 2, guaranteed by RESTART IDENTITY on an
    empty table) so profile_id foreign keys in items/posts/threads/runs
    have something to reference.
    """
    db.init_db()
    with db.connect() as conn:
        for t in _TABLES:
            conn.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE")
        conn.execute(
            "INSERT INTO profiles (slug, display_name) VALUES "
            "('test-profile-1', 'Test Profile 1'), "
            "('test-profile-2', 'Test Profile 2')"
        )
    yield
