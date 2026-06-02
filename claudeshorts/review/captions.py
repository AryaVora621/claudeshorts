"""Per-platform caption + hashtag formatting.

Two consumers share this module so the text a human approves in the review
queue is exactly what ships next to the exported video:
- the dashboard review page (rendered inline, one block per platform), and
- the publish exporter (``caption.txt`` beside each platform's MP4).

Keeping the formatting here (not in either caller) is what guarantees that
parity.
"""

from __future__ import annotations

from typing import Any, Callable


def _hashtags(tags: Any) -> str:
    """Join hashtags into one space-separated line, each prefixed with '#'."""
    out: list[str] = []
    for tag in tags or []:
        text = str(tag).strip()
        if not text:
            continue
        out.append("#" + text.lstrip("#"))
    return " ".join(out)


def youtube_caption(captions: dict[str, Any]) -> str:
    """YouTube wants a title line, a 1-2 line description, then hashtags."""
    block = (captions or {}).get("youtube", {}) or {}
    lines: list[str] = []
    if block.get("title"):
        lines.append(str(block["title"]).strip())
    if block.get("description"):
        lines.append(str(block["description"]).strip())
    tags = _hashtags(block.get("hashtags"))
    if tags:
        lines.append(tags)
    return "\n".join(lines).strip()


def _short_caption(captions: dict[str, Any], platform: str) -> str:
    """TikTok / Instagram: a single caption line followed by hashtags."""
    block = (captions or {}).get(platform, {}) or {}
    lines: list[str] = []
    if block.get("caption"):
        lines.append(str(block["caption"]).strip())
    tags = _hashtags(block.get("hashtags"))
    if tags:
        lines.append(tags)
    return "\n".join(lines).strip()


def tiktok_caption(captions: dict[str, Any]) -> str:
    return _short_caption(captions, "tiktok")


def instagram_caption(captions: dict[str, Any]) -> str:
    return _short_caption(captions, "instagram")


# Platform -> formatter. The dashboard iterates this to render the review page;
# the exporter looks up the matching platform when writing caption.txt.
PLATFORM_CAPTION: dict[str, Callable[[dict[str, Any]], str]] = {
    "youtube": youtube_caption,
    "tiktok": tiktok_caption,
    "instagram": instagram_caption,
}


def captions_markdown(post: dict[str, Any]) -> str:
    """Human-readable ``captions.md`` bundling every platform for review."""
    caps = post.get("captions") or {}
    parts = [f"# {post.get('title', '(untitled)')}", ""]
    for platform, fn in PLATFORM_CAPTION.items():
        parts += [f"## {platform.capitalize()}", "", fn(caps) or "(none)", ""]
    return "\n".join(parts).strip() + "\n"
