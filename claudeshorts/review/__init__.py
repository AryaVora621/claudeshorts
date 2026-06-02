"""Review queue: bundle rendered posts for human approval.

The review *bundle* (media + captions + manifest) is assembled here; the
dashboard (``claudeshorts.dashboard``) serves and acts on it. Approval hands off
to ``claudeshorts.publish`` for the assisted export.
"""

from .captions import PLATFORM_CAPTION, captions_markdown
from .queue import assemble_review, pending_reviews, review_dir_for

__all__ = [
    "assemble_review",
    "pending_reviews",
    "review_dir_for",
    "PLATFORM_CAPTION",
    "captions_markdown",
]
