"""Deterministic, config-driven style choices applied after Claude
generates a post — no LLM prompting involved, so the same subject/topic
always renders with the same recognizable color and layout."""

from __future__ import annotations


def pin_brand_colors(theme: dict, brand_colors: dict) -> dict:
    subject = (theme.get("subject") or "").lower()
    match_key = None
    for key in brand_colors:
        if key.lower() in subject:
            if match_key is None or len(key) > len(match_key):
                match_key = key
    if match_key is None:
        return theme
    palette = brand_colors[match_key]
    return {**theme, **palette, "subject": theme.get("subject")}


def select_layout(item: dict, layout_rules: dict, default_layout: str) -> str:
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    for layout, keywords in layout_rules.items():
        if any(kw.lower() in haystack for kw in keywords):
            return layout
    return default_layout
