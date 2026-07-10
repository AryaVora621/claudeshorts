from __future__ import annotations

from unittest.mock import patch

from claudeshorts.jobs import registry


def test_all_six_job_types_registered():
    expected = {"full_run", "ingest", "generate", "generate_from_item", "render_post"}
    assert expected <= set(registry.JOB_HANDLERS)


def test_generate_from_item_unpacks_payload():
    with patch("claudeshorts.services.pipeline_service.generate_for_item") as mock_fn:
        mock_fn.return_value = {"post_id": 5}
        result = registry.JOB_HANDLERS["generate_from_item"]({"item_id": 5})
        mock_fn.assert_called_once_with(5)
        assert result == {"post_id": 5}


def test_render_post_unpacks_payload():
    with patch("claudeshorts.services.pipeline_service.render_post_service") as mock_fn:
        mock_fn.return_value = {
            "frames": 40, "duration_ms": 5000, "audio_mode": "tts", "review_dir": "/review/7",
        }
        result = registry.JOB_HANDLERS["render_post"]({"post_id": 7})
        mock_fn.assert_called_once_with(7)
        assert result == "rendered post 7: 40 frames, 5000ms, audio=tts"
