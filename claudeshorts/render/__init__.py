"""Render bridge: hand a post spec to the Node renderer (Playwright + ffmpeg).

Public entrypoint: ``render_post``.
"""

from .bridge import build_spec, render_post

__all__ = ["render_post", "build_spec"]
