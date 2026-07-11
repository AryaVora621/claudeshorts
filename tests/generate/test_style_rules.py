from __future__ import annotations

from claudeshorts.generate.style_rules import pin_brand_colors, select_layout

BRAND_COLORS = {
    "nvidia": {"primary": "#76B900", "secondary": "#0A0A0A", "accent": "#FFFFFF", "mood": "dark"},
    "google": {"primary": "#4285F4", "secondary": "#0A0A0A", "accent": "#FFFFFF", "mood": "dark"},
    "google deepmind": {"primary": "#8E44AD", "secondary": "#0A0A0A", "accent": "#FFFFFF", "mood": "dark"},
}


def _theme(subject: str) -> dict:
    return {"subject": subject, "primary": "#111111", "secondary": "#222222",
            "accent": "#333333", "mood": "light"}


def test_pin_brand_colors_exact_match():
    result = pin_brand_colors(_theme("Nvidia"), BRAND_COLORS)
    assert result["primary"] == "#76B900"
    assert result["mood"] == "dark"


def test_pin_brand_colors_case_insensitive_substring():
    result = pin_brand_colors(_theme("Nvidia's new Blackwell chip"), BRAND_COLORS)
    assert result["primary"] == "#76B900"


def test_pin_brand_colors_longest_match_wins():
    result = pin_brand_colors(_theme("Google DeepMind ships Gemini 4"), BRAND_COLORS)
    assert result["primary"] == "#8E44AD"


def test_pin_brand_colors_no_match_returns_unchanged():
    original = _theme("Some Unknown Startup")
    result = pin_brand_colors(original, BRAND_COLORS)
    assert result == original


def test_pin_brand_colors_preserves_subject_field():
    result = pin_brand_colors(_theme("Nvidia"), BRAND_COLORS)
    assert result["subject"] == "Nvidia"


LAYOUT_RULES = {
    "breaking": ["launch", "launches", "announces", "unveils"],
    "editorial": ["analysis", "opinion", "deep dive", "explainer"],
}


def test_select_layout_matches_breaking():
    item = {"title": "Nvidia launches new GPU", "summary": ""}
    assert select_layout(item, LAYOUT_RULES, "slideshow") == "breaking"


def test_select_layout_matches_editorial_in_summary():
    item = {"title": "What happened this week", "summary": "A deep dive into the news."}
    assert select_layout(item, LAYOUT_RULES, "slideshow") == "editorial"


def test_select_layout_first_match_wins_in_rule_order():
    item = {"title": "Analysis: OpenAI launches a new model"}
    assert select_layout(item, LAYOUT_RULES, "slideshow") == "breaking"


def test_select_layout_no_match_returns_default():
    item = {"title": "Just a regular update", "summary": "Nothing special."}
    assert select_layout(item, LAYOUT_RULES, "slideshow") == "slideshow"


def test_select_layout_empty_rules_returns_default():
    assert select_layout({"title": "anything"}, {}, "slideshow") == "slideshow"
