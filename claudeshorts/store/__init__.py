"""SQLite store: schema, connections, and thin data-access helpers.

Holds both the raw ingested `items` and the pipeline's content memory
(`posts`, `threads`, `post_threads`) so the selection/generation steps can
dedupe and build follow-ups across days.
"""

from .db import SCHEMA, connect, init_db
from .items import count_items, insert_item

__all__ = ["SCHEMA", "connect", "init_db", "insert_item", "count_items"]
