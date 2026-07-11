"""SQLite store: schema, connections, and thin data-access helpers.

Holds both the raw ingested `items` and the pipeline's content memory
(`posts`, `threads`, `post_threads`) so the selection/generation steps can
dedupe and build follow-ups across days.
"""

from .db import SCHEMA, connect, init_db
from .items import (
    count_items, get_item, get_items, insert_item, insert_manual_item,
    latest_items, recent_items,
)
from .pins import is_pinned, pin_item, pinned_item_ids, pinned_items, unpin_item
from .posts import (
    all_posts, due_posts, get_post, insert_post, posts_by_status, recent_posts,
    scheduled_posts, set_schedule, set_status, status_counts, used_item_ids,
)
from .profiles import (
    get_profile, get_profile_by_id, list_profiles, set_auto_publish, upsert_profile,
)
from .threads import (
    link_post_thread, open_threads, posts_for_thread, threads_with_posts,
    upsert_thread,
)

__all__ = [
    "SCHEMA", "connect", "init_db",
    "insert_item", "insert_manual_item", "count_items", "recent_items",
    "latest_items", "get_item", "get_items",
    "insert_post", "get_post", "recent_posts", "posts_by_status", "all_posts",
    "status_counts", "used_item_ids", "set_status",
    "set_schedule", "scheduled_posts", "due_posts",
    "pin_item", "unpin_item", "is_pinned", "pinned_item_ids", "pinned_items",
    "open_threads", "upsert_thread", "link_post_thread",
    "posts_for_thread", "threads_with_posts",
    "upsert_profile", "get_profile", "get_profile_by_id", "list_profiles",
    "set_auto_publish",
]
