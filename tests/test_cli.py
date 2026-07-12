from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from claudeshorts.cli import app
from claudeshorts.store import connect, init_db
from claudeshorts.store.profiles import upsert_profile

runner = CliRunner()


@pytest.fixture(autouse=True)
def _seed_default_profile():
    """The CLI resolves a stopgap default profile ("fork-ai") before calling
    into pipeline_service (see cli._default_profile_id); the commands under
    test here mock pipeline_service itself, so the only real DB dependency
    left is that lookup succeeding."""
    init_db()
    with connect() as conn:
        upsert_profile(conn, slug="fork-ai", display_name="fork.ai")
        conn.commit()
    yield


def test_ingest_cmd_calls_pipeline_service():
    with patch("claudeshorts.cli.pipeline_service.run_ingest_service") as mock_fn:
        mock_fn.return_value = {
            "fetched": 1, "stored": 1, "duplicates": 0, "skipped_old": 0,
            "total_items": 1, "by_source": {},
        }
        result = runner.invoke(app, ["ingest"])
    assert result.exit_code == 0
    mock_fn.assert_called_once()


def test_generate_cmd_calls_pipeline_service():
    with patch("claudeshorts.cli.pipeline_service.run_generate_service") as mock_fn:
        mock_fn.return_value = [
            {"post_id": 1, "thread_slug": "some-thread", "title": "Some title", "follow_up": False},
        ]
        result = runner.invoke(app, ["generate"])
    assert result.exit_code == 0
    mock_fn.assert_called_once()
    assert "generated=1" in result.stdout


def test_render_cmd_calls_pipeline_service_and_prints_summary():
    with patch("claudeshorts.cli.pipeline_service.render_post_service") as mock_fn:
        mock_fn.return_value = {
            "frames": 40, "duration_ms": 5000, "audio_mode": "tts", "review_dir": "/review/7",
        }
        result = runner.invoke(app, ["render", "7"])
    assert result.exit_code == 0
    mock_fn.assert_called_once_with(7)
    assert "rendered post #7: 40 frames, 5000ms, audio=tts" in result.stdout
    assert "review folder: /review/7" in result.stdout


def test_render_cmd_missing_post_exits_nonzero():
    with patch("claudeshorts.cli.pipeline_service.render_post_service") as mock_fn:
        mock_fn.side_effect = ValueError("no post 999")
        result = runner.invoke(app, ["render", "999"])
    assert result.exit_code == 1
    assert "no post 999" in result.output


def test_run_cmd_calls_pipeline_service():
    with patch("claudeshorts.cli.pipeline_service.run_full_pipeline_service") as mock_fn:
        mock_fn.return_value = {"skipped": True, "reason": "already ran", "date": "2026-07-10"}
        result = runner.invoke(app, ["run"])
    assert result.exit_code == 0
    mock_fn.assert_called_once()
