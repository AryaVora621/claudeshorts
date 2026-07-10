# Chunk 14: Additional LLM Provider API Keys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all friction from wiring a real remote/local LLM vendor into chunk 7's already-built provider abstraction — exact config presets, setup docs, and a connection-test CLI command — without requiring any real credentials in this session.

**Architecture:** Config comments + a doc file (no code) plus one new Typer command in `claudeshorts/cli.py` that exercises chunk 7's `providers.registry`/`OpenAICompatibleProvider` path with a trivial test payload.

**Tech Stack:** Python 3.11+, existing `typer`, chunk 7's `claudeshorts.generate.providers`.

## Global Constraints

- No comments explaining *what*, only non-obvious *why*.
- The test command must never dump a raw stack trace to the terminal — friendly pass/fail only.
- Full spec: `docs/superpowers/specs/2026-07-10-chunk14-llm-provider-keys-design.md`.

---

## File Structure

- Modify: `config/settings.yaml`, `.env.example`, `claudeshorts/cli.py`
- Create: `docs/LLM_PROVIDER_SETUP.md`
- Test: `tests/cli/test_test_model_backend.py`

---

### Task 1: Config presets + setup doc + `.env.example`

**Files:**
- Modify: `config/settings.yaml`, `.env.example`
- Create: `docs/LLM_PROVIDER_SETUP.md`

- [ ] **Step 1: Add the commented presets to `config/settings.yaml`**

Below the existing `model.openai_compat`/`model.local` blocks (chunk 7),
add the comment block exactly as specified:

```yaml
  openai_compat:
    base_url: ""          # e.g. https://openrouter.ai/api/v1
    model: ""
    api_key_env: "OPENAI_COMPAT_API_KEY"
    # --- copy-paste presets (uncomment ONE, fill in model, set the env var) ---
    # OpenRouter:  base_url: "https://openrouter.ai/api/v1"
    #              model: "anthropic/claude-sonnet-4.6"  (or any OpenRouter-listed model)
    # NVIDIA NIM:  base_url: "https://integrate.api.nvidia.com/v1"
    #              model: "meta/llama-3.1-70b-instruct"  (or any NIM-hosted model)
    # Gemini:      base_url: "https://generativelanguage.googleapis.com/v1beta/openai/"
    #              model: "gemini-2.5-flash"  (or any Gemini model, via its OpenAI-compat endpoint)
  local:
    base_url: "http://127.0.0.1:11434/v1"   # Ollama default
    model: "qwen3-30b-a3b"
    # --- alternates ---
    # LM Studio:  base_url: "http://127.0.0.1:1234/v1"
    # vLLM:       base_url: "http://127.0.0.1:8000/v1"
```

- [ ] **Step 2: Write `docs/LLM_PROVIDER_SETUP.md`**

```markdown
# LLM provider setup

claudeshorts defaults to `model.backend: claude_cli` (your Claude Pro/Max
subscription, no API key). This doc covers wiring an alternative backend
— useful if you want a free local model, or a specific remote vendor.

## Remote (openai_compat)

1. Get an API key:
   - **OpenRouter**: https://openrouter.ai/keys
   - **NVIDIA NIM**: https://build.nvidia.com (API catalog, per-model keys)
   - **Gemini**: https://aistudio.google.com/apikey
2. Set it: `export OPENAI_COMPAT_API_KEY=sk-...` (or add to `.env`).
3. In `config/settings.yaml`, set `model.backend: openai_compat` and fill
   in `model.openai_compat.base_url`/`model` from the presets in that
   file (one vendor at a time — switching vendors means editing these two
   fields, not adding a second slot).
4. Verify: `claudeshorts test-model-backend --backend openai_compat`

## Local (Ollama / LM Studio / vLLM)

1. Install and run one of them locally (e.g. `ollama pull qwen3:30b-a3b && ollama serve`).
2. Set `model.backend: local` in `config/settings.yaml`; `model.local
   .base_url` already defaults to Ollama's `http://127.0.0.1:11434/v1` —
   change it to `http://127.0.0.1:1234/v1` (LM Studio) or
   `http://127.0.0.1:8000/v1` (vLLM) if using one of those instead.
3. No API key needed.
4. Verify: `claudeshorts test-model-backend --backend local`
```

- [ ] **Step 3: Add the `.env.example` entry**

```
# Only needed if model.backend: openai_compat in config/settings.yaml —
# see docs/LLM_PROVIDER_SETUP.md for how to get a key for your chosen vendor.
OPENAI_COMPAT_API_KEY=
```

- [ ] **Step 4: Commit**

```bash
git add config/settings.yaml .env.example docs/LLM_PROVIDER_SETUP.md
git commit -m "docs: add per-vendor LLM provider config presets and setup guide"
```

---

### Task 2: `test-model-backend` CLI command

**Files:**
- Modify: `claudeshorts/cli.py`
- Test: `tests/cli/test_test_model_backend.py`

**Interfaces:**
- Consumes: `claudeshorts.generate.providers.registry.get_provider` (chunk 7).
- Produces: `claudeshorts test-model-backend [--backend NAME]` — prints a pass/fail message, exits 0 or 1.

- [ ] **Step 1: Write the failing tests**

```python
# tests/cli/test_test_model_backend.py
from __future__ import annotations

from typer.testing import CliRunner

from claudeshorts.cli import app

runner = CliRunner()


def test_reports_success(monkeypatch):
    class FakeProvider:
        def generate_structured(self, system, user_prompt, tool_schema, tool_name):
            return {"ok": True}

    monkeypatch.setattr(
        "claudeshorts.cli.registry.get_provider", lambda name, **kw: FakeProvider(),
    )
    result = runner.invoke(app, ["test-model-backend", "--backend", "local"])
    assert result.exit_code == 0
    assert "reachable" in result.stdout.lower()


def test_reports_failure_without_stack_trace(monkeypatch):
    class FailingProvider:
        def generate_structured(self, system, user_prompt, tool_schema, tool_name):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(
        "claudeshorts.cli.registry.get_provider", lambda name, **kw: FailingProvider(),
    )
    result = runner.invoke(app, ["test-model-backend", "--backend", "local"])
    assert result.exit_code == 1
    assert "connection refused" in result.stdout
    assert "Traceback" not in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_test_model_backend.py -v`
Expected: FAIL — `AssertionError` (no such command registered) or `RuntimeError` surfacing as an uncaught exception

- [ ] **Step 3: Implement the command in `cli.py`**

Add near the top of `claudeshorts/cli.py` (alongside existing imports):

```python
from .generate.providers import registry
```

Add the command (near the other `@app.command(...)` definitions):

```python
_TEST_TOOL = {
    "name": "test_ok",
    "description": "Return a trivial ok flag to confirm the backend responds correctly.",
    "input_schema": {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    },
}


@app.command("test-model-backend")
def test_model_backend_cmd(
    backend: str = typer.Option(None, help="claude_cli|api|local|openai_compat; defaults to config's model.backend"),
) -> None:
    """Send one trivial prompt through the configured provider and report pass/fail."""
    name = backend or settings().get("model", {}).get("backend", "claude_cli")
    try:
        provider = registry.get_provider(name)
        result = provider.generate_structured(
            system="You are a test.",
            user_prompt='Reply with a JSON object {"ok": true}.',
            tool_schema=_TEST_TOOL,
            tool_name="test_ok",
        )
        if not result.get("ok"):
            raise ValueError(f"unexpected response: {result!r}")
    except Exception as exc:
        typer.echo(f"✗ {name} failed: {exc}")
        raise typer.Exit(code=1)
    typer.echo(f"✓ {name} reachable and responding correctly.")
```

(`settings` is already imported in `cli.py` per its existing commands —
confirm via `grep -n "^from .config import\|^from \.\. import config" claudeshorts/cli.py`
and adjust the import line to match whatever name is already in scope.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cli/test_test_model_backend.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full CLI test suite to check for regressions**

Run: `pytest tests/cli/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/cli.py tests/cli/test_test_model_backend.py
git commit -m "feat: add test-model-backend CLI command for quick provider connectivity checks"
```

---

### Task 3: Final checkpoint — all 14 chunks planned

**Files:**
- Modify: `CHECKPOINT_LAST.md`, `TASK_QUEUE.md`

- [ ] **Step 1: Record completion of the full 14-chunk planning effort**

Update `TASK_QUEUE.md` to move chunk 14 to Done and note that **all 14
chunks of the goal.md platform rebuild now have committed spec + plan
documents** (chunks 9 and 13 are research-notes-only by design, not
implementation plans, per their "research now, implement later" scope).
Update `CHECKPOINT_LAST.md` with a summary: what's been planned, what
remains genuinely human-required across the whole rebuild (Supabase
migration execution, real API credentials for LLM/publishing, real
Telegram bot token, real browser logins, Higgsfield/Veo cost decision),
and that implementation has not yet started for any chunk — next action
is for the user to choose which chunk(s) to actually implement first
(chunks 1-9 have no human-required blockers and could be implemented
immediately; chunks 10-14 have real, explicitly-flagged human-required
final steps within their otherwise-complete plans).

- [ ] **Step 2: Commit**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 14 complete — all 14 goal.md rebuild chunks now speced and planned"
```

---

## Self-Review Notes

**Spec coverage:** Config presets (Task 1 Step 1) match the spec's exact
per-vendor `base_url` values. `docs/LLM_PROVIDER_SETUP.md` (Task 1 Step 2)
covers both remote and local paths per the spec. `.env.example` (Task 1
Step 3) matches the spec's single-line addition. `test-model-backend`
(Task 2) matches the spec's friendly-pass-fail, no-stack-trace, reuses-
chunk-7's-code-path requirements exactly — it calls
`generate_structured` with a real (trivial) `tool_schema`, so it
genuinely exercises the same translation logic
(`OpenAICompatibleProvider`'s Anthropic-tool-shape-to-OpenAI-function-
shape conversion) that real generation depends on, not a separate,
unfaithful health check.

**Placeholder scan:** Task 2 Step 3 includes an explicit instruction to
confirm `cli.py`'s existing `settings` import name before adding the new
import — flagged because this plan doesn't have `cli.py`'s exact current
import list in front of it, not because the step is incomplete. No other
placeholder patterns found.

**Type consistency:** `_TEST_TOOL`'s shape
(`{"name", "description", "input_schema"}`) matches `schema.POST_TOOL`'s
shape from chunk 7, so it flows through `registry.get_provider(...)
.generate_structured(system, user_prompt, tool_schema, tool_name)`
identically to real post generation — no special-cased test-only code
path inside any provider.
