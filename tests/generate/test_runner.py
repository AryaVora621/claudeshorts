from __future__ import annotations

from claudeshorts.generate.runner import generate_for_item
from claudeshorts.store import connect
from claudeshorts.store.items import insert_manual_item
from claudeshorts.store.posts import get_post


def _fake_generated_post(item, prior_coverage=None, **kw):
    return {
        "title": "T",
        "thread_slug": "t",
        "thread_title": "T",
        "thread_summary": "S",
        "theme": {
            "subject": "Nvidia", "primary": "#111111",
            "secondary": "#222222", "accent": "#333333", "mood": "light",
        },
        "slides": [{"headline": "H", "bullets": []}] * 3,
        "captions": {
            "youtube": {"title": "t", "description": "d", "hashtags": []},
            "tiktok": {"caption": "c", "hashtags": []},
            "instagram": {"caption": "c", "hashtags": []},
        },
    }


def test_generate_for_item_pins_brand_colors_and_selects_layout():
    with connect() as conn:
        item_id, _ = insert_manual_item(
            conn, title="Nvidia launches new GPU", summary=""
        )
        conn.commit()

    # Pass generate_fn explicitly rather than monkeypatching the module-level
    # `generate_post` symbol: it's bound as generate_for_item's default arg
    # value at import time, so patching the module attribute after import
    # would not affect calls that omit generate_fn.
    result = generate_for_item(item_id, generate_fn=_fake_generated_post)

    with connect() as conn:
        post = get_post(conn, result["post_id"])

    assert post["theme"]["primary"] == "#76B900"
    assert post["layout"] == "breaking"


def test_generate_for_item_no_match_falls_back_to_default_layout():
    with connect() as conn:
        item_id, _ = insert_manual_item(
            conn, title="Just a regular update", summary="Nothing special."
        )
        conn.commit()

    result = generate_for_item(item_id, generate_fn=_fake_generated_post)

    with connect() as conn:
        post = get_post(conn, result["post_id"])

    assert post["layout"] == "slideshow"
