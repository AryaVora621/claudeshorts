# Chunk 14: Additional LLM provider API keys

## Context

Fourteenth and final chunk of the goal.md platform rebuild. Chunk 7
already built the full provider abstraction (`LLMProvider` Protocol,
`OpenAICompatibleProvider` registered as both `local` and `openai_compat`,
config sections, registry). What remains is genuinely human-required:
obtaining real API keys for OpenRouter/NVIDIA NIM/Gemini/etc. and pointing
`config/settings.yaml` at them. That step cannot happen in this planning
session. What *can* be done now — and is the actual content of this
chunk's plan — is everything that removes friction from that future
5-minute step: exact per-vendor config presets, setup documentation, and a
connection-test command that reports a clear pass/fail without requiring
this session to hold any real credentials.

## Decision

No new abstractions — chunk 7's `LLMProvider`/`OpenAICompatibleProvider`/
registry are already correct and sufficient. This chunk adds:

1. **Per-vendor config presets** — exact, copy-pasteable
   `base_url`/`model` values for every vendor goal.md names, as commented
   examples in `config/settings.yaml` and spelled out in a new
   `docs/LLM_PROVIDER_SETUP.md`.
2. **A connection-test CLI command** — `claudeshorts test-model-backend`
   — calls the configured (or a named) provider with a trivial prompt and
   reports success/failure clearly, so the user knows immediately after
   pasting in a key whether it works, without needing to run a full
   generation cycle to find out.
3. **`.env.example` documentation** for exactly which env var name each
   vendor's key goes into.

## Architecture

### `config/settings.yaml` — per-vendor preset comments

Below the existing `model.openai_compat` block (chunk 7), add commented
reference presets (inert until uncommented and filled in):

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

### `docs/LLM_PROVIDER_SETUP.md` (new)

A short walkthrough per vendor: where to get a key (OpenRouter dashboard,
NVIDIA NIM API catalog, Google AI Studio for Gemini), which env var to set
(`OPENAI_COMPAT_API_KEY` per chunk 7's config, or a vendor-specific
override via `api_key_env` if the user wants multiple vendors configured
simultaneously — noting that only one `openai_compat` slot exists today,
so switching vendors means editing `base_url`/`model`, not stacking
multiple), and the exact `config/settings.yaml` edit to make. Ends with
"then run `claudeshorts test-model-backend --backend openai_compat` to
verify."

### `claudeshorts test-model-backend` CLI command

New Typer command in `claudeshorts/cli.py`, alongside the existing
`init-db`/`ingest`/`generate`/etc. commands:

```python
@app.command("test-model-backend")
def test_model_backend_cmd(
    backend: str = typer.Option(None, help="claude_cli|api|local|openai_compat; defaults to config's model.backend"),
) -> None:
    """Send one trivial prompt through the configured provider and report pass/fail."""
```

Implementation calls `providers.registry.get_provider(backend or
cfg["backend"])` then `.generate_structured(system="You are a test.",
user_prompt="Reply with a JSON object {\"ok\": true}.", tool_schema=
_TEST_TOOL, tool_name="test_ok")` where `_TEST_TOOL` is a minimal
Anthropic-tool-shaped schema (`{"name": "test_ok", "input_schema":
{"type": "object", "properties": {"ok": {"type": "boolean"}},
"required": ["ok"]}}`) — reused as-is by `OpenAICompatibleProvider`'s
existing schema-translation logic (chunk 7), so this test genuinely
exercises the same code path real generation uses, just with a trivial
payload instead of a full post. On success prints "✓ <backend> reachable
and responding correctly." On any exception, prints "✗ <backend> failed:
<message>" and exits with status 1 — no stack trace dump, since this
command's whole purpose is a friendly, fast pass/fail check for a
non-developer running it right after pasting in a key.

### `.env.example` addition

```
# Only needed if model.backend: openai_compat in config/settings.yaml —
# see docs/LLM_PROVIDER_SETUP.md for how to get a key for your chosen vendor.
OPENAI_COMPAT_API_KEY=
```//
(No entry needed for `local` — Ollama/LM Studio/vLLM require no API key.)

## Out of scope for this chunk

- Actually obtaining any real API key or running `test-model-backend`
  against a live vendor — the explicit final human-required step, same
  pattern as every other deferred chunk.
- Supporting more than one `openai_compat` vendor configured
  simultaneously (e.g. OpenRouter AND NVIDIA both active) — today's
  single `openai_compat` config slot is a deliberate chunk-7 scope
  decision; switching vendors means editing config, not adding a second
  slot. Revisit only if genuinely running two remote vendors side-by-side
  becomes a real need.
- Cost/rate-limit tracking per vendor — out of scope until real usage
  exists to measure.

## Testing

`tests/cli/test_test_model_backend.py` — the command calls
`registry.get_provider` with the right backend name and prints the
success message when the (mocked) provider returns `{"ok": True}`; prints
the failure message and exits 1 when the provider raises. Mirrors chunk
7/8's HTTP-mocking test pattern — no real network calls, no real
credentials needed to verify this command's own logic.
