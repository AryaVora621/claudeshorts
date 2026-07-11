"""Subscription-auth Claude backend: shells to the `claude` CLI in headless
print mode. Moved from generate/generator.py verbatim (chunk 7 extraction,
no behavior change) — the CLI path relies on the schema being described in
the prompt text itself (see generator.build_cli_prompt), so tool_schema/
tool_name are accepted for interface conformance but unused here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


class ClaudeCLIProvider:
    def __init__(self, cli_model: str = "sonnet", timeout_seconds: int = 180):
        self.cli_model = cli_model
        self.timeout_seconds = timeout_seconds

    def generate_structured(
        self, system: str, user_prompt: str, tool_schema: dict, tool_name: str,
    ) -> dict:
        raw = self._run_cli(user_prompt)
        return self._parse_json_object(self._result_text(raw))

    def _run_cli(self, prompt: str) -> str:
        binary = shutil.which("claude") or "claude"
        try:
            proc = subprocess.run(
                [binary, "-p", "--output-format", "json", "--model", self.cli_model],
                input=prompt, capture_output=True, text=True, timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "`claude` CLI not found. Install Claude Code and run `claude login` "
                "to use the subscription backend, or set model.backend: api."
            ) from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"claude CLI failed (exit {proc.returncode}): {detail}")
        return proc.stdout

    def _result_text(self, raw: str) -> str:
        try:
            env = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        events = env if isinstance(env, list) else [env]
        result_event = next(
            (e for e in reversed(events)
             if isinstance(e, dict) and e.get("type") == "result"),
            None,
        )
        if result_event is not None:
            if result_event.get("is_error"):
                detail = (result_event.get("result")
                          or result_event.get("api_error_status") or "unknown error")
                raise RuntimeError(f"claude CLI returned an error result: {detail}")
            text = result_event.get("result")
            if isinstance(text, str):
                return text
        if isinstance(env, dict) and isinstance(env.get("result"), str):
            return env["result"]
        texts = [
            block.get("text", "")
            for e in events if isinstance(e, dict) and e.get("type") == "assistant"
            for block in (e.get("message", {}).get("content") or [])
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if texts:
            return "\n".join(texts)
        return raw

    def _parse_json_object(self, text: str) -> dict:
        s = (text or "").strip()
        start, end = s.find("{"), s.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("no JSON object found in Claude output")
        return json.loads(s[start:end + 1])
