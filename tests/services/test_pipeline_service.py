from __future__ import annotations

from unittest.mock import patch

import pytest

from claudeshorts.services import pipeline_service


def test_run_ingest_service_delegates():
    with patch("claudeshorts.services.pipeline_service.run_ingest") as mock_fn:
        mock_fn.return_value = {"fetched": 1}
        result = pipeline_service.run_ingest_service(since="2026-01-01", limit=5)
    mock_fn.assert_called_once_with(since="2026-01-01", limit=5)
    assert result == {"fetched": 1}


def test_run_generate_service_delegates():
    with patch("claudeshorts.services.pipeline_service.run_generate") as mock_fn:
        mock_fn.return_value = [{"post_id": 1}]
        result = pipeline_service.run_generate_service(limit=3)
    mock_fn.assert_called_once_with(limit=3, on_progress=None)
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
        result = pipeline_service.run_full_pipeline_service(force=True)
    mock_fn.assert_called_once_with(limit=None, force=True, skip_render=False)
    assert result == {"date": "2026-07-10"}
