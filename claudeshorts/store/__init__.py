"""SQLite store: schema, connections, and thin data-access helpers.

Holds both the raw ingested `items` and the pipeline's content memory
(`posts`, `threads`, `post_threads`) so the selection/generation steps can
dedupe and build follow-ups across days.
"""

from .db import SCHEMA, connect, init_db
from .items import count_items, insert_item, recent_items
from .posts import get_post, insert_post, recent_posts, set_status, used_item_ids
from .threads import link_post_thread, open_threads, upsert_thread

__all__ = [
    "SCHEMA", "connect", "init_db",
    "insert_item", "count_items", "recent_items",
    "insert_post", "get_post", "recent_posts", "used_item_ids", "set_status",
    "open_threads", "upsert_thread", "link_post_thread",
]
