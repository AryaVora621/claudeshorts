"""Assemble the human review bundle for a rendered post.

On render we copy the produced media into ``review/<date>/post_<id>/`` alongside
a human-readable ``captions.md`` and a machine ``manifest.json``, then mark the
post ``rendered`` so it surfaces in the dashboard review queue. Nothing here
publishes — approval (and export) is a separate, deliberate human step.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from .. import config
from ..store import connect, posts_by_status, set_status
from .captions import captions_markdown


def review_dir_for(post_id: int, on_date: str | None = None) -> Path:
    """Return the review folder for a post.

    Prefers the most recent existing ``review/<date>/post_<id>/`` (a post can be
    re-rendered on a later day); otherwise the path for ``on_date`` (today).
    """
    existing = sorted(config.REVIEW_DIR.glob(f"*/post_{post_id}"))
    if existing:
        return existing[-1]
    day = on_date or date.today().isoformat()
    return config.REVIEW_DIR / day / f"post_{post_id}"


def assemble_review(post: dict[str, Any], result: dict[str, Any]) -> Path:
    """Build the review bundle from a render result; mark the post ``rendered``.

    ``result`` is the renderer's JSON (see ``render.bridge.render_post``):
    ``{video, thumb, duration_ms, frames, audio_mode}`` with absolute paths.
    """
    config.ensure_dirs()
    today = date.today().isoformat()
    dest = config.REVIEW_DIR / today / f"post_{post['id']}"
    dest.mkdir(parents=True, exist_ok=True)

    for key, name in (("video", "video.mp4"), ("thumb", "thumb.png")):
        src = result.get(key)
        if src and Path(src).exists():
            shutil.copy2(src, dest / name)

    # Per-slide stills for the swipeable carousel (Instagram/TikTok). Mirror the
    # renderer's slides/ folder so the bundle holds both the video and the deck.
    slide_names: list[str] = []
    slides = [s for s in (result.get("slides") or []) if s and Path(s).exists()]
    if slides:
        slides_dir = dest / "slides"
        slides_dir.mkdir(parents=True, exist_ok=True)
        for src in slides:
            name = Path(src).name
            shutil.copy2(src, slides_dir / name)
            slide_names.append(name)

    (dest / "captions.md").write_text(captions_markdown(post), encoding="utf-8")
    (dest / "manifest.json").write_text(
        json.dumps(
            {
                "post_id": post["id"],
                "title": post.get("title"),
                "theme": post.get("theme"),
                "date": today,
                "frames": result.get("frames"),
                "duration_ms": result.get("duration_ms"),
                "audio_mode": result.get("audio_mode"),
                "slides": slide_names,
                "captions": post.get("captions"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with connect() as conn:
        set_status(conn, post["id"], "rendered")
        conn.commit()
    return dest


def carousel_slides(post_id: int) -> list[str]:
    """Filenames of a post's swipeable deck stills, sorted, or [] if none.

    Looks in the review bundle first (what the dashboard serves), then the raw
    render dir, so it works before and after a post is assembled for review.
    Posts that predate carousel rendering simply have no ``slides/`` folder.
    """
    for base in (review_dir_for(post_id) / "slides",
                 config.RENDERS_DIR / f"post_{post_id}" / "slides"):
        if base.is_dir():
            names = sorted(p.name for p in base.glob("slide_*.png"))
            if names:
                return names
    return []


def pending_reviews() -> list[dict[str, Any]]:
    """Rendered posts awaiting a human approve/reject decision."""
    with connect() as conn:
        return posts_by_status(conn, "rendered")
