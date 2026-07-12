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

    Seeds profile id 1 with slug "fork-ai" (guaranteed by RESTART IDENTITY on
    an empty table) so profile_id foreign keys have something to reference,
    and so `load_prompt`/`load_sources` resolve against a real
    config/profiles/fork-ai/ directory rather than a synthetic slug.
    """
    db.init_db()
    with db.connect() as conn:
        for t in _TABLES:
            conn.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE")
        conn.execute(
            "INSERT INTO profiles (slug, display_name) VALUES ('fork-ai', 'fork.ai')"
        )
    yield
