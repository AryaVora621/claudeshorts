"""Structured-output contract for generated posts.

`POST_TOOL` is an Anthropic tool definition used with forced tool_choice so
Claude returns a structured object instead of prose. `validate_post` re-checks
the shape so we never persist a malformed post (and so the logic is verifiable
offline without calling Claude).
"""

from __future__ import annotations

import re
from typing import Any

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

POST_TOOL: dict[str, Any] = {
    "name": "emit_post",
    "description": (
        "Emit the structured short-form post (slides + per-platform captions) "
        "for the given tech/AI news item."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Punchy hook/title for the short (<= 70 chars).",
            },
            "thread_slug": {
                "type": "string",
                "description": "Stable kebab-case id for the ongoing storyline, "
                               "e.g. 'gpt-5-launch'. Reuse the provided slug on follow-ups.",
            },
            "thread_title": {"type": "string"},
            "thread_summary": {
                "type": "string",
                "description": "1-2 sentence running summary of the storyline, "
                               "updated to include this item.",
            },
            "theme": {
                "type": "object",
                "description": "Color theme matching the SUBJECT of the news "
                               "(the company/product/topic), NOT the channel brand. "
                               "e.g. Nvidia -> green on black; Anthropic -> clay/orange "
                               "on warm gray; OpenAI -> teal on black.",
                "properties": {
                    "subject": {"type": "string",
                                "description": "Brand/company/topic the theme reflects, e.g. 'Nvidia'."},
                    "primary": {"type": "string", "description": "Primary hex, e.g. '#76B900'."},
                    "secondary": {"type": "string", "description": "Background hex, e.g. '#0A0A0A'."},
                    "accent": {"type": "string", "description": "Highlight hex, e.g. '#FFFFFF'."},
                    "mood": {"type": "string", "enum": ["dark", "light"]},
                },
                "required": ["subject", "primary", "secondary", "accent", "mood"],
            },
            "slides": {
                "type": "array",
                "minItems": 3,
                "maxItems": 7,
                "items": {
                    "type": "object",
                    "properties": {
                        "headline": {"type": "string"},
                        "bullets": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 3,
                        },
                        "voiceover": {"type": "string"},
                        "visual_hint": {"type": "string"},
                    },
                    "required": ["headline", "bullets"],
                },
            },
            "captions": {
                "type": "object",
                "properties": {
                    "youtube": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "hashtags": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["title", "description", "hashtags"],
                    },
                    "tiktok": {
                        "type": "object",
                        "properties": {
                            "caption": {"type": "string"},
                            "hashtags": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["caption", "hashtags"],
                    },
                    "instagram": {
                        "type": "object",
                        "properties": {
                            "caption": {"type": "string"},
                            "hashtags": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["caption", "hashtags"],
                    },
                },
                "required": ["youtube", "tiktok", "instagram"],
            },
        },
        "required": [
            "title", "thread_slug", "thread_title", "thread_summary",
            "theme", "slides", "captions",
        ],
    },
}

_PLATFORM_REQUIRED = {
    "youtube": ("title", "description", "hashtags"),
    "tiktok": ("caption", "hashtags"),
    "instagram": ("caption", "hashtags"),
}


def validate_post(data: Any) -> list[str]:
    """Return a list of structural errors; empty list means valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["post is not an object"]

    for key in ("title", "thread_slug", "thread_title", "thread_summary"):
        if not isinstance(data.get(key), str) or not data.get(key):
            errors.append(f"missing/empty string field: {key}")

    theme = data.get("theme")
    if not isinstance(theme, dict):
        errors.append("theme must be an object")
    else:
        if theme.get("mood") not in ("dark", "light"):
            errors.append("theme.mood must be 'dark' or 'light'")
        if not theme.get("subject"):
            errors.append("theme.subject missing")
        for color in ("primary", "secondary", "accent"):
            value = theme.get(color)
            if not isinstance(value, str) or not _HEX_RE.match(value):
                errors.append(f"theme.{color} must be a hex color")

    slides = data.get("slides")
    if not isinstance(slides, list) or not (3 <= len(slides) <= 7):
        errors.append("slides must be a list of 3-7 items")
    else:
        for i, slide in enumerate(slides):
            if not isinstance(slide, dict) or not slide.get("headline"):
                errors.append(f"slide {i}: missing headline")
            if not isinstance(slide.get("bullets"), list):
                errors.append(f"slide {i}: bullets must be a list")

    captions = data.get("captions")
    if not isinstance(captions, dict):
        errors.append("captions must be an object")
    else:
        for platform, fields in _PLATFORM_REQUIRED.items():
            block = captions.get(platform)
            if not isinstance(block, dict):
                errors.append(f"captions.{platform} missing")
                continue
            for f in fields:
                if f not in block:
                    errors.append(f"captions.{platform}.{f} missing")
    return errors
