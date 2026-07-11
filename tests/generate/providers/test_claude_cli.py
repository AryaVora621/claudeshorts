from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from claudeshorts.generate.providers.claude_cli import ClaudeCLIProvider


def _fake_proc(stdout: str, returncode: int = 0):
    class P:
        pass
    p = P()
    p.stdout, p.stderr, p.returncode = stdout, "", returncode
    return p


def test_generate_structured_parses_result_event():
    envelope = json.dumps([{"type": "result", "result": '{"title": "T"}'}])
    with patch("subprocess.run", return_value=_fake_proc(envelope)):
        provider = ClaudeCLIProvider(cli_model="sonnet")
        result = provider.generate_structured("sys", "user", {}, "emit_post")
    assert result == {"title": "T"}


def test_generate_structured_raises_on_cli_error():
    with patch("subprocess.run", return_value=_fake_proc("boom", returncode=1)):
        provider = ClaudeCLIProvider(cli_model="sonnet")
        with pytest.raises(RuntimeError, match="claude CLI failed"):
            provider.generate_structured("sys", "user", {}, "emit_post")


def test_generate_structured_raises_if_cli_missing():
    with patch("shutil.which", return_value=None), \
         patch("subprocess.run", side_effect=FileNotFoundError()):
        provider = ClaudeCLIProvider(cli_model="sonnet")
        with pytest.raises(RuntimeError, match="claude` CLI not found"):
            provider.generate_structured("sys", "user", {}, "emit_post")
