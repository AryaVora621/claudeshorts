from __future__ import annotations

from unittest.mock import patch

import pytest

from claudeshorts.services import pipeline_service


def test_run_ingest_service_delegates():
    with patch("claudeshorts.services.pipeline_service.run_ingest") as mock_fn:
        mock_fn.return_value = {"fetched": 1}
        result = pipeline_service.run_ingest_service(profile_id=42, since="2026-01-01", limit=5)
    mock_fn.assert_called_once_with(42, since="2026-01-01", limit=5)
    assert result == {"fetched": 1}


def test_run_ingest_service_requires_profile_id(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "claudeshorts.services.pipeline_service.run_ingest",
        lambda profile_id, since=None, limit=None: captured.update(profile_id=profile_id) or {},
    )
    pipeline_service.run_ingest_service(profile_id=42)
    assert captured["profile_id"] == 42


def test_run_generate_service_delegates():
    with patch("claudeshorts.services.pipeline_service.run_generate") as mock_fn:
        mock_fn.return_value = [{"post_id": 1}]
        result = pipeline_service.run_generate_service(profile_id=42, limit=3)
    mock_fn.assert_called_once_with(42, limit=3, on_progress=None)
    assert result == [{"post_id": 1}]


def test_render_post_service_not_found_raises():
    with pytest.raises(ValueError, match="no post"):
        pipeline_service.render_post_service(999999)


def test_render_post_service_renders_and_assembles():
    with patch("claudeshorts.services.pipeline_service.get_post") as mock_get, \
         patch("claudeshorts.services.pipeline_service.render_post") as mock_render, \
         patch("claudeshorts.services.pipeline_service.assemble_review") as mock_assemble:
        mock_get.return_value = {"id": 7}
        mock_render.return_value = {"frames": 40, "duration_ms": 5000, "audio_mode": "tts"}
        mock_assemble.return_value = "/review/7"
        result = pipeline_service.render_post_service(7)
    mock_render.assert_called_once_with({"id": 7})
    mock_assemble.assert_called_once_with(
        {"id": 7}, {"frames": 40, "duration_ms": 5000, "audio_mode": "tts"},
    )
    assert result == {
        "frames": 40, "duration_ms": 5000, "audio_mode": "tts", "review_dir": "/review/7",
    }


def test_run_full_pipeline_service_delegates():
    with patch("claudeshorts.services.pipeline_service.run_pipeline") as mock_fn:
        mock_fn.return_value = {"date": "2026-07-10"}
        result = pipeline_service.run_full_pipeline_service(profile_id=42, force=True)
    mock_fn.assert_called_once_with(42, limit=None, force=True, skip_render=False)
    assert result == {"date": "2026-07-10"}


def test_drain_scheduled_posts_service_delegates():
    with patch("claudeshorts.services.pipeline_service.publish_due_posts") as mock_fn:
        mock_fn.return_value = [1, 2]
        result = pipeline_service.drain_scheduled_posts_service()
    mock_fn.assert_called_once_with()
    assert result == [1, 2]
