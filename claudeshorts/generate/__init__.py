"""Claude generation: select topics, build slides + per-platform captions.

Reads content memory (threads/posts) to dedupe and write follow-ups instead of
repeating prior coverage.

Public entrypoints: ``select_topics``, ``generate_post``, ``run_generate``.
"""

from .generator import generate_post
from .runner import run_generate
from .select import select_topics

__all__ = ["select_topics", "generate_post", "run_generate"]
