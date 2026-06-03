"""Assisted publish: export an approved post for manual upload.

Copies the rendered MP4 plus a per-platform ``caption.txt`` into
``publish/<platform>/<date>/post_<id>/`` and marks the post ``exported`` (with a
``published_at`` stamp that feeds content memory). API automation is deliberately
deferred — a human does the final upload from these folders.
"""

from __future__ import annotations

import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .. import config, progress
from ..review.captions import PLATFORM_CAPTION
from ..review.queue import review_dir_for
from ..store import connect, due_posts, set_status


def _locate_video(post_id: int) -> Path:
    """Find the rendered MP4 (review bundle first, then the raw render dir)."""
    candidate = review_dir_for(post_id) / "video.mp4"
    if candidate.exists():
        return candidate
    fallback = config.RENDERS_DIR / f"post_{post_id}" / "video.mp4"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(
        f"no rendered video for post {post_id} — render it before exporting."
    )


def _locate_slides(post_id: int) -> list[Path]:
    """Find the per-slide carousel PNGs (review bundle first, then render dir).

    Returns the slide images sorted by filename (slide_01, slide_02, …), or an
    empty list if this post predates carousel rendering.
    """
    for base in (review_dir_for(post_id) / "slides",
                 config.RENDERS_DIR / f"post_{post_id}" / "slides"):
        if base.is_dir():
            stills = sorted(base.glob("slide_*.png"))
            if stills:
                return stills
    return []


def export_post(
    post: dict[str, Any], platforms: list[str] | None = None
) -> list[Path]:
    """Export one post to every configured platform folder. Returns the dirs."""
    config.ensure_dirs()
    cfg = config.settings()
    platforms = platforms or cfg.get("platforms", ["youtube", "tiktok", "instagram"])

    video = _locate_video(post["id"])
    slides = _locate_slides(post["id"])
    today = date.today().isoformat()
    caps = post.get("captions") or {}

    out_dirs: list[Path] = []
    for platform in platforms:
        dest = config.PUBLISH_DIR / platform / today / f"post_{post['id']}"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(video, dest / "video.mp4")
        # Also drop the swipeable carousel so the post can go out as a slideshow
        # (Instagram/TikTok) instead of the auto-advancing video.
        if slides:
            slides_dest = dest / "slides"
            slides_dest.mkdir(parents=True, exist_ok=True)
            for still in slides:
                shutil.copy2(still, slides_dest / still.name)
        formatter = PLATFORM_CAPTION.get(platform)
        text = formatter(caps) if formatter else ""
        (dest / "caption.txt").write_text(text + "\n", encoding="utf-8")
        out_dirs.append(dest)

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as conn:
        set_status(conn, post["id"], "exported", published_at=stamp)
        conn.commit()
    return out_dirs


def publish_due_posts(on_date: str | None = None) -> list[int]:
    """Export every approved, scheduled post whose date has arrived.

    Called at the tail of the daily run to drain the future-posts queue. Posts
    not yet rendered are skipped (not an error); export flips them to
    ``exported`` so a later run won't republish them.
    """
    on_date = on_date or date.today().isoformat()
    with connect() as conn:
        due = due_posts(conn, on_date)

    published: list[int] = []
    total = len(due)
    for i, post in enumerate(due, 1):
        progress.step(i, total, f"exporting post {post['id']}")
        try:
            export_post(post)
        except FileNotFoundError:
            continue
        published.append(post["id"])
    return published
