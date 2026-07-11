"""Test platform context binding in export_post."""
from __future__ import annotations

import logging

from claudeshorts import logging_setup
from claudeshorts.publish import exporter


def test_export_post_logs_with_platform_bound(monkeypatch, tmp_path, caplog):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    monkeypatch.setattr(exporter, "_locate_video", lambda post_id: video)
    monkeypatch.setattr(exporter, "_locate_slides", lambda post_id: [])
    post = {"id": 1, "captions": {}}

    # Attach the context filter to caplog's handler so it processes contextvars
    context_filter = logging_setup._ContextFilter()
    caplog.handler.addFilter(context_filter)

    with caplog.at_level(logging.INFO, logger="claudeshorts.publish"):
        exporter.export_post(post, platforms=["youtube", "tiktok"])

    platforms_seen = {r.platform for r in caplog.records if getattr(r, "platform", None)}
    assert platforms_seen == {"youtube", "tiktok"}
