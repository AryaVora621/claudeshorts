from __future__ import annotations

from claudeshorts.render.bridge import build_spec


def test_build_spec_includes_layout():
    post = {"theme": {}, "layout": "breaking", "slides": [], "captions": {}}
    spec = build_spec(post)
    assert spec["layout"] == "breaking"


def test_build_spec_defaults_layout_to_slideshow_when_missing():
    post = {"theme": {}, "slides": [], "captions": {}}
    spec = build_spec(post)
    assert spec["layout"] == "slideshow"
