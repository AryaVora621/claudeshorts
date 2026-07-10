# Chunk 7: LLM Provider Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract an `LLMProvider` Protocol and four concrete providers (`claude_cli`, `api`, `local`, `openai_compat`) from today's Claude-only two-backend `generate/generator.py`, with zero behavior change for the two existing backends and real (mockable-for-test) generic OpenAI-compatible support for local and remote non-Claude models.

**Architecture:** New `claudeshorts/generate/providers/` package. `generator.py::generate_post` becomes a thin dispatcher calling `providers.registry.get_provider(backend).generate_structured(...)`.

**Tech Stack:** Python 3.11+, `httpx` (already a dependency) for the OpenAI-compatible HTTP client, no new dependencies.

## Global Constraints

- Python 3.11+, type hints everywhere, PEP 8.
- No comments explaining *what*, only non-obvious *why*.
- Zero behavior change for `claude_cli`/`api` backends — existing tests for `generate_post` must pass unmodified in intent (imports may need updating).
- Full spec: `docs/superpowers/specs/2026-07-10-chunk7-llm-provider-design.md`.

---

## File Structure

- Create: `claudeshorts/generate/providers/__init__.py`, `base.py`, `claude_cli.py`, `claude_api.py`, `openai_compatible.py`, `registry.py`
- Modify: `claudeshorts/generate/generator.py` — becomes a thin dispatcher
- Modify: `config/settings.yaml` — `model.local`/`model.openai_compat` sections
- Modify: `claudeshorts/dashboard/settings_io.py` — widen allowed backend list
- Create: `tests/generate/providers/test_claude_cli.py`, `test_claude_api.py`, `test_openai_compatible.py`, `test_registry.py`

---

### Task 1: `base.py` Protocol + `claude_cli.py` provider

**Files:**
- Create: `claudeshorts/generate/providers/__init__.py` (empty)
- Create: `claudeshorts/generate/providers/base.py`
- Create: `claudeshorts/generate/providers/claude_cli.py`
- Test: `tests/generate/providers/test_claude_cli.py`

**Interfaces:**
- Produces: `LLMProvider` Protocol (`generate_structured(system, user_prompt, tool_schema, tool_name) -> dict`), `ClaudeCLIProvider(cli_model: str, timeout_seconds: int = 180)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/generate/providers/test_claude_cli.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/generate/providers/test_claude_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.generate.providers'`

- [ ] **Step 3: Implement `base.py` and `claude_cli.py`**

```python
# claudeshorts/generate/providers/base.py
"""The shared interface every LLM provider implements — goal.md: never
hardcode providers, always code against an interface. `tool_schema`/
`tool_name` describe the structured output every caller wants; each
provider is responsible for whatever mechanism its backend uses to
enforce that shape (Claude's forced tool_choice, OpenAI-compatible
function calling, etc.)."""

from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    def generate_structured(
        self, system: str, user_prompt: str, tool_schema: dict, tool_name: str,
    ) -> dict: ...
```

```python
# claudeshorts/generate/providers/claude_cli.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/generate/providers/test_claude_cli.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/generate/providers/__init__.py claudeshorts/generate/providers/base.py claudeshorts/generate/providers/claude_cli.py tests/generate/providers/test_claude_cli.py
git commit -m "feat: extract LLMProvider protocol and ClaudeCLIProvider"
```

---

### Task 2: `claude_api.py` provider

**Files:**
- Create: `claudeshorts/generate/providers/claude_api.py`
- Test: `tests/generate/providers/test_claude_api.py`

**Interfaces:**
- Produces: `ClaudeAPIProvider(model: str = "claude-sonnet-4-6", client: Any | None = None, prompt_cache: bool = True, max_tokens: int = 4096)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/generate/providers/test_claude_api.py
from __future__ import annotations

from unittest.mock import MagicMock

from claudeshorts.generate.providers.claude_api import ClaudeAPIProvider


def test_generate_structured_extracts_tool_use_block():
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit_post"
    block.input = {"title": "T"}
    message = MagicMock()
    message.content = [block]
    client = MagicMock()
    client.messages.create.return_value = message

    provider = ClaudeAPIProvider(client=client, model="claude-sonnet-4-6")
    result = provider.generate_structured(
        "sys", "user", {"name": "emit_post", "input_schema": {}}, "emit_post",
    )
    assert result == {"title": "T"}
    _, kwargs = client.messages.create.call_args
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_post"}


def test_generate_structured_raises_if_no_tool_use_block():
    message = MagicMock()
    message.content = []
    client = MagicMock()
    client.messages.create.return_value = message

    provider = ClaudeAPIProvider(client=client, model="claude-sonnet-4-6")
    import pytest
    with pytest.raises(ValueError, match="no emit_post tool_use block"):
        provider.generate_structured("sys", "user", {}, "emit_post")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/generate/providers/test_claude_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.generate.providers.claude_api'`

- [ ] **Step 3: Implement `claude_api.py`**

```python
"""Direct Anthropic API backend (metered ANTHROPIC_API_KEY), forced tool use.
Moved from generate/generator.py — chunk 7 extraction, no behavior change,
except tool_schema/tool_name now come from the caller instead of the
hardcoded POST_TOOL/"emit_post" constants."""

from __future__ import annotations

from typing import Any


class ClaudeAPIProvider:
    def __init__(
        self, model: str = "claude-sonnet-4-6", client: Any | None = None,
        prompt_cache: bool = True, max_tokens: int = 4096,
    ):
        self.model = model
        self._client = client
        self.prompt_cache = prompt_cache
        self.max_tokens = max_tokens

    def _client_or_default(self) -> Any:
        if self._client is not None:
            return self._client
        from anthropic import Anthropic
        return Anthropic()

    def generate_structured(
        self, system: str, user_prompt: str, tool_schema: dict, tool_name: str,
    ) -> dict:
        client = self._client_or_default()
        if self.prompt_cache:
            system_arg: Any = [{
                "type": "text", "text": system, "cache_control": {"type": "ephemeral"},
            }]
        else:
            system_arg = system
        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_arg,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user_prompt}],
        )
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                return block.input
        raise ValueError(f"Claude response contained no {tool_name} tool_use block")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/generate/providers/test_claude_api.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/generate/providers/claude_api.py tests/generate/providers/test_claude_api.py
git commit -m "feat: extract ClaudeAPIProvider"
```

---

### Task 3: `openai_compatible.py` generic provider

**Files:**
- Create: `claudeshorts/generate/providers/openai_compatible.py`
- Test: `tests/generate/providers/test_openai_compatible.py`

**Interfaces:**
- Produces: `OpenAICompatibleProvider(base_url: str, model: str, api_key: str | None = None, timeout_seconds: int = 180)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/generate/providers/test_openai_compatible.py
from __future__ import annotations

import json

import httpx
import pytest

from claudeshorts.generate.providers.openai_compatible import OpenAICompatibleProvider


def _mock_transport(response_json):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, json=response_json)
    return httpx.MockTransport(handler)


def _tool_call_response(arguments: dict):
    return {
        "choices": [{
            "message": {
                "tool_calls": [{
                    "function": {"name": "emit_post", "arguments": json.dumps(arguments)},
                }],
            },
        }],
    }


def test_generate_structured_parses_tool_call(monkeypatch):
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="qwen3")
    monkeypatch.setattr(
        provider, "_client",
        httpx.Client(transport=_mock_transport(_tool_call_response({"title": "T"}))),
    )
    result = provider.generate_structured(
        "sys", "user", {"name": "emit_post", "input_schema": {"type": "object"}}, "emit_post",
    )
    assert result == {"title": "T"}


def test_generate_structured_sends_bearer_token_when_api_key_set(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=_tool_call_response({"title": "T"}))

    provider = OpenAICompatibleProvider(
        base_url="https://openrouter.ai/api/v1", model="some/model", api_key="sk-test",
    )
    monkeypatch.setattr(provider, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    provider.generate_structured("sys", "user", {"name": "emit_post", "input_schema": {}}, "emit_post")
    assert seen["auth"] == "Bearer sk-test"


def test_generate_structured_raises_if_no_tool_call(monkeypatch):
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="qwen3")
    empty = {"choices": [{"message": {}}]}
    monkeypatch.setattr(provider, "_client", httpx.Client(transport=_mock_transport(empty)))
    with pytest.raises(ValueError, match="no emit_post tool call"):
        provider.generate_structured("sys", "user", {"name": "emit_post", "input_schema": {}}, "emit_post")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/generate/providers/test_openai_compatible.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.generate.providers.openai_compatible'`

- [ ] **Step 3: Implement `openai_compatible.py`**

```python
"""Generic OpenAI-compatible chat-completions client. One implementation
covers every provider that speaks this de facto standard: Ollama/LM
Studio/vLLM locally (registered as `local`), and OpenRouter/NVIDIA
NIM/Gemini/OpenAI itself remotely (registered as `openai_compat`) — the
difference is only `base_url`/`api_key`/`model` in config, never new code.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class OpenAICompatibleProvider:
    def __init__(
        self, base_url: str, model: str, api_key: str | None = None,
        timeout_seconds: int = 180,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self._client = httpx.Client(timeout=timeout_seconds)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate_structured(
        self, system: str, user_prompt: str, tool_schema: dict, tool_name: str,
    ) -> dict:
        function_spec = {
            "type": "function",
            "function": {
                "name": tool_schema.get("name", tool_name),
                "description": tool_schema.get("description", ""),
                "parameters": tool_schema.get("input_schema", {"type": "object"}),
            },
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            "tools": [function_spec],
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
        }
        resp = self._client.post(
            f"{self.base_url}/chat/completions", json=body, headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        message = data["choices"][0]["message"]
        for call in message.get("tool_calls") or []:
            if call["function"]["name"] == tool_name:
                return json.loads(call["function"]["arguments"])
        raise ValueError(f"{self.base_url} response contained no {tool_name} tool call")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/generate/providers/test_openai_compatible.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/generate/providers/openai_compatible.py tests/generate/providers/test_openai_compatible.py
git commit -m "feat: add generic OpenAICompatibleProvider (covers local + remote OpenAI-compatible APIs)"
```

---

### Task 4: `registry.py` + `generator.py` dispatcher + config/settings_io

**Files:**
- Create: `claudeshorts/generate/providers/registry.py`
- Modify: `claudeshorts/generate/generator.py`
- Modify: `config/settings.yaml`
- Modify: `claudeshorts/dashboard/settings_io.py`
- Test: `tests/generate/providers/test_registry.py`, `tests/generate/test_generator.py` (existing — must still pass)

**Interfaces:**
- Produces: `get_provider(name: str, *, client=None, model=None) -> LLMProvider`

- [ ] **Step 1: Write the failing tests**

```python
# tests/generate/providers/test_registry.py
from __future__ import annotations

import pytest

from claudeshorts.generate.providers import registry
from claudeshorts.generate.providers.claude_cli import ClaudeCLIProvider
from claudeshorts.generate.providers.claude_api import ClaudeAPIProvider
from claudeshorts.generate.providers.openai_compatible import OpenAICompatibleProvider


def test_get_provider_claude_cli():
    provider = registry.get_provider("claude_cli")
    assert isinstance(provider, ClaudeCLIProvider)


def test_get_provider_api():
    provider = registry.get_provider("api")
    assert isinstance(provider, ClaudeAPIProvider)


def test_get_provider_local():
    provider = registry.get_provider("local")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert "11434" in provider.base_url


def test_get_provider_openai_compat():
    provider = registry.get_provider("openai_compat")
    assert isinstance(provider, OpenAICompatibleProvider)


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError, match="unknown model.backend"):
        registry.get_provider("not-a-real-backend")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/generate/providers/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.generate.providers.registry'`

- [ ] **Step 3: Add config sections**

Extend `config/settings.yaml`'s existing `model:` section with:
```yaml
model:
  # ... existing backend/cli_model/name/etc. keys unchanged ...
  local:
    base_url: "http://127.0.0.1:11434/v1"
    model: "qwen3-30b-a3b"
  openai_compat:
    base_url: ""
    model: ""
    api_key_env: "OPENAI_COMPAT_API_KEY"
```

- [ ] **Step 4: Implement `registry.py`**

```python
"""Maps a `model.backend` config string to a live provider instance. Reads
config lazily per call (matching the rest of the codebase's `settings()`
pattern) so a settings.yaml edit takes effect without a restart-sensitive
module-level cache.
"""

from __future__ import annotations

import os
from typing import Any

from ...config import settings
from .claude_api import ClaudeAPIProvider
from .claude_cli import ClaudeCLIProvider
from .openai_compatible import OpenAICompatibleProvider


def get_provider(name: str, *, client: Any | None = None, model: str | None = None):
    cfg = settings().get("model", {})
    if name == "claude_cli":
        return ClaudeCLIProvider(
            cli_model=cfg.get("cli_model", "sonnet"),
            timeout_seconds=cfg.get("timeout_seconds", 180),
        )
    if name == "api":
        return ClaudeAPIProvider(
            model=model or cfg.get("name", "claude-sonnet-4-6"),
            client=client,
            prompt_cache=cfg.get("prompt_cache", True),
            max_tokens=cfg.get("max_tokens", 4096),
        )
    if name == "local":
        local_cfg = cfg.get("local", {})
        return OpenAICompatibleProvider(
            base_url=local_cfg.get("base_url", "http://127.0.0.1:11434/v1"),
            model=local_cfg.get("model", ""),
        )
    if name == "openai_compat":
        oc_cfg = cfg.get("openai_compat", {})
        return OpenAICompatibleProvider(
            base_url=oc_cfg.get("base_url", ""),
            model=oc_cfg.get("model", ""),
            api_key=os.environ.get(oc_cfg.get("api_key_env", "OPENAI_COMPAT_API_KEY")),
        )
    raise ValueError(f"unknown model.backend: {name!r} (use claude_cli|api|local|openai_compat)")
```

- [ ] **Step 5: Run registry test to verify it passes**

Run: `pytest tests/generate/providers/test_registry.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Rewrite `generate_post` in `claudeshorts/generate/generator.py` as a thin dispatcher**

Remove `_run_claude_cli`, `_result_text`, `_parse_json_object`,
`_generate_via_cli`, `_make_client`, `_extract_tool_input`,
`_generate_via_api` (all now live in `providers/`). Replace `generate_post`
with:

```python
from .providers import registry
from . import schema

def generate_post(
    item: dict, prior_coverage: str | None = None, *,
    client: Any | None = None, model: str | None = None, backend: str | None = None,
) -> dict:
    """Generate one validated structured post via the configured backend."""
    cfg = settings().get("model", {})
    backend = backend or cfg.get("backend", "claude_cli")
    provider = registry.get_provider(backend, client=client, model=model)
    data = provider.generate_structured(
        SYSTEM_PROMPT, build_user_prompt(item, prior_coverage),
        schema.POST_TOOL, "emit_post",
    )
    errors = schema.validate_post(data)
    if errors:
        raise ValueError("invalid post from model: " + "; ".join(errors))
    return data
```

Keep `SYSTEM_PROMPT`, `build_user_prompt`, `build_cli_prompt` in
`generator.py` unchanged (still used — `build_cli_prompt`'s output should
now be produced by folding its schema-in-prompt-text behavior into
`ClaudeCLIProvider`'s prompt construction; check whether `build_cli_prompt`
vs `build_user_prompt` selection logic needs to move into
`ClaudeCLIProvider.generate_structured` — if `generate_post` no longer
distinguishes CLI vs API prompt building, `ClaudeCLIProvider` must call
`build_cli_prompt` itself rather than receiving a pre-built `user_prompt`.
Resolve this by having `ClaudeCLIProvider.generate_structured` ignore the
passed `user_prompt` in favor of re-deriving the CLI-specific prompt
form is wrong layering — instead, move the cli-vs-api prompt choice into
`generator.py`'s dispatcher: pass `build_cli_prompt(...)` when
`backend == "claude_cli"`, else `build_user_prompt(...)`, before calling
`provider.generate_structured`. Update the dispatcher accordingly:

```python
def generate_post(
    item: dict, prior_coverage: str | None = None, *,
    client: Any | None = None, model: str | None = None, backend: str | None = None,
) -> dict:
    cfg = settings().get("model", {})
    backend = backend or cfg.get("backend", "claude_cli")
    prompt = (build_cli_prompt(item, prior_coverage) if backend == "claude_cli"
              else build_user_prompt(item, prior_coverage))
    provider = registry.get_provider(backend, client=client, model=model)
    data = provider.generate_structured(SYSTEM_PROMPT, prompt, schema.POST_TOOL, "emit_post")
    errors = schema.validate_post(data)
    if errors:
        raise ValueError("invalid post from model: " + "; ".join(errors))
    return data
```

This is the version to actually ship — the earlier snippet in this step
was wrong and is superseded by this one.)

- [ ] **Step 7: Widen the allowed backend list in `settings_io.py`**

In `claudeshorts/dashboard/settings_io.py`, find the line checking
`if backend not in ("claude_cli", "api"):` and change it to:
```python
    if backend not in ("claude_cli", "api", "local", "openai_compat"):
```

- [ ] **Step 8: Run the full generate test suite to check for regressions**

Run: `pytest tests/generate/ -v`
Expected: PASS — update any existing `tests/generate/test_generator.py`
tests that patched now-removed private functions
(`_generate_via_cli`/`_generate_via_api`/`_make_client`) to instead patch
`claudeshorts.generate.providers.registry.get_provider` or construct a
fake provider directly, following the same "update the pinned
implementation detail" approach used in chunk 3's Task 4.

- [ ] **Step 9: Commit**

```bash
git add claudeshorts/generate/providers/registry.py claudeshorts/generate/generator.py config/settings.yaml claudeshorts/dashboard/settings_io.py tests/generate/providers/test_registry.py tests/generate/test_generator.py
git commit -m "feat: generate_post dispatches through providers.registry; widen allowed backends"
```

---

### Task 5: Update checkpoint and task tracking

**Files:**
- Modify: `CHECKPOINT_LAST.md`, `TASK_QUEUE.md`

- [ ] **Step 1: Record completion**

Update `TASK_QUEUE.md` to move chunk 7 to Done. Update `CHECKPOINT_LAST.md`
with next action: chunk 8 (more video/renderer styles).

- [ ] **Step 2: Commit**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 7 complete — LLM provider abstraction with generic local/remote support live"
```

---

## Self-Review Notes

**Spec coverage:** `LLMProvider` Protocol (Task 1) matches the spec's
single-method interface. `ClaudeCLIProvider`/`ClaudeAPIProvider` (Tasks 1-2)
are verbatim extractions with no behavior change, matching the spec's
explicit requirement. `OpenAICompatibleProvider` (Task 3) matches the
spec's "one implementation, two registrations" design — `local` and
`openai_compat` both instantiate it, differing only by config (Task 4).
Settings/settings_io changes (Task 4 Steps 3, 7) match the spec's config
additions and the one-line allowed-backend widening.

**Placeholder scan:** Task 4 Step 6 shows its own reasoning correction
inline (an initially-wrong approach to where CLI-vs-API prompt selection
belongs, then the corrected version) rather than presenting only a clean
final answer — flagged explicitly as "this is the version to actually
ship" so an implementer doesn't accidentally apply the superseded snippet.

**Type consistency:** `generate_structured`'s 4-argument signature
(`system, user_prompt, tool_schema, tool_name`) is identical across all
three provider implementations and the registry's return type — verified
consistent in Tasks 1, 2, 3, and the dispatcher in Task 4. `tool_schema`'s
expected shape (`{"name", "description", "input_schema"}`, Anthropic's
native tool format) is consumed correctly by both `ClaudeAPIProvider`
(passed through as-is) and `OpenAICompatibleProvider` (translated to
OpenAI's `{"type": "function", "function": {...}}` shape) — this
translation point is the one place format differences are handled, not
scattered across callers.
