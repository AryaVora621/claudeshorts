"""Assisted publishing: export approved posts to ``publish/<platform>/`` folders.

The pipeline never auto-uploads. Export prepares an upload-ready bundle (MP4 +
caption) per platform; a human does the final post. The export seam is where a
real platform API (YouTube Data API first) would later attach.
"""

from .exporter import export_post, publish_due_posts

__all__ = ["export_post", "publish_due_posts"]
