# Chunk 7: LLM provider abstraction

## Context

Seventh of 14 chunks rebuilding claudeshorts per `goal.md` (see
`TASK_QUEUE.md` / session task list). goal.md wants LLM providers
(Claude/Gemini/OpenAI/OpenRouter/NVIDIA/Ollama/LM Studio/vLLM) implemented
as plugins behind a shared interface, never hardcoded. Per the earlier
chunk-ordering decision, this chunk is interface-plus-generic-
implementation — Claude stays the only *default* wired backend, but unlike
a pure-stub approach, this chunk ships real generic providers usable the
moment a user supplies a `base_url`/`api_key`, without writing new code per
vendor.

## Current state

`claudeshorts/generate/generator.py` has two "backends" — `claude_cli`
(shells to the `claude` CLI, subscription auth) and `api` (direct Anthropic
SDK call with forced tool use) — both Claude-only, selected by
`model.backend` in `config/settings.yaml`. The prompt-building
(`build_cli_prompt`/`build_user_prompt`), Claude-tool-schema
(`schema.POST_TOOL`), and JSON-extraction/validation logic are already
decoupled from the two backend functions — only `_generate_via_cli` and
`_generate_via_api` are Claude-specific.

Home-server memory (`local-model-backend.md`) already anticipates running
Qwen3-30B-A3B GGUF on the P40 via Ollama/llama.cpp as a free local
alternative — this chunk's `local` provider is exactly the abstraction that
plan needs to slot into.

## Decision (confirmed with user)

Define an `LLMProvider` Protocol with one method:

```python
class LLMProvider(Protocol):
    def generate_structured(
        self, system: str, user_prompt: str, tool_schema: dict, tool_name: str,
    ) -> dict: ...
```

Four concrete providers, registered by name in
`claudeshorts/generate/providers/registry.py`:

- **`claude_cli`** — today's subscription-auth path, refactored to
  implement the Protocol (unchanged behavior).
- **`api`** — today's direct Anthropic SDK path, refactored to implement
  the Protocol (unchanged behavior).
- **`local`** — a **generic OpenAI-compatible chat-completions client**
  (`base_url` defaults to `http://127.0.0.1:11434/v1` for Ollama, no API
  key required) — this one implementation covers Ollama, LM Studio, and
  vLLM/llama.cpp's OpenAI-compatible server mode, since they all speak the
  same `/chat/completions` + `tools` request shape. Which local runtime is
  actually running is just a `base_url`/`model` config choice, not
  different code.
- **`openai_compat`** — the same generic client pointed at a remote
  `base_url` + `api_key` — covers OpenRouter, NVIDIA NIM, and Gemini (which
  exposes an OpenAI-compatible endpoint at
  `generativelanguage.googleapis.com/v1beta/openai/`), and OpenAI itself,
  all through one implementation. Vendor choice is `base_url` + `api_key`
  + `model` in config, not a new class.

This means **no stub/NotImplementedError providers are needed** — every
provider goal.md names is reachable through one of these four concrete
implementations, configured rather than coded. Selecting `local` or
`openai_compat` without a reachable server / valid key produces a clear
runtime error (connection refused / 401), which is expected and acceptable
— the code path exists and works the moment credentials do, satisfying
"leave human-required tasks for last" without blocking the abstraction
itself.

## Architecture

### `claudeshorts/generate/providers/` (new package)

- `base.py` — the `LLMProvider` Protocol.
- `claude_cli.py` — `ClaudeCLIProvider`, wrapping today's
  `_run_claude_cli`/`_result_text`/`_parse_json_object` (moved here
  verbatim, `tool_schema`/`tool_name` accepted but unused since the CLI
  path relies on prompt-embedded schema instructions, exactly as today).
- `claude_api.py` — `ClaudeAPIProvider`, wrapping today's
  `_generate_via_api`/`_extract_tool_input` (moved here, using
  `tool_schema`/`tool_name` to build the `tools=[...]` /
  `tool_choice={"type": "tool", "name": tool_name}` call instead of the
  hardcoded `POST_TOOL`/`"emit_post"`).
- `openai_compatible.py` — `OpenAICompatibleProvider(base_url, api_key,
  model, timeout=180)`, implementing `generate_structured` via
  `httpx.post(f"{base_url}/chat/completions", json={"model":..., "tools":
  [...], "tool_choice": {"type": "function", "function": {"name":
  tool_name}}, "messages": [...]})` (OpenAI tool-calling shape), extracting
  `tool_calls[0].function.arguments` (a JSON string) and parsing it.
  Registered twice under different names/configs (`local`, `openai_compat`)
  — same class, different constructor args from settings.
- `registry.py` — `PROVIDERS: dict[str, Callable[[], LLMProvider]]`
  (factories, not instances, so config is read lazily at call time,
  matching today's `settings()`-per-call pattern) and `get_provider(name:
  str) -> LLMProvider`.

### `config/settings.yaml` additions

```yaml
model:
  backend: claude_cli   # claude_cli | api | local | openai_compat
  cli_model: sonnet
  name: claude-sonnet-4-6
  local:
    base_url: "http://127.0.0.1:11434/v1"
    model: "qwen3-30b-a3b"
  openai_compat:
    base_url: ""          # e.g. https://openrouter.ai/api/v1
    model: ""
    api_key_env: "OPENAI_COMPAT_API_KEY"
```

### `generator.py` after this chunk

`generate_post` becomes a thin dispatcher:

```python
def generate_post(item, prior_coverage=None, *, client=None, model=None, backend=None) -> dict:
    cfg = settings().get("model", {})
    backend = backend or cfg.get("backend", "claude_cli")
    provider = providers.get_provider(backend)
    raw = provider.generate_structured(
        SYSTEM_PROMPT, build_user_prompt(item, prior_coverage),
        schema.POST_TOOL, "emit_post",
    )
    errors = validate_post(raw)
    if errors:
        raise ValueError("invalid post from model: " + "; ".join(errors))
    return raw
```

(`client`/`model` params retained for the `api` backend's existing test
injection points — `get_provider` passes them through to
`ClaudeAPIProvider`'s constructor when `backend == "api"`.)

## Out of scope for this chunk

- Actually running/testing against a live Ollama/OpenRouter/NVIDIA/Gemini
  endpoint — that requires a reachable local server or a real API key,
  both human-required. Tests mock the HTTP layer (`httpx` responses)
  instead.
- Per-vendor quirks (e.g. Gemini's exact OpenAI-compat endpoint path,
  OpenRouter's model-name conventions) — `base_url`/`model` are just config
  strings the user fills in; this chunk doesn't validate them against any
  particular vendor's actual API.
- Provider selection UI in the dashboard beyond what `settings_backend`
  already does (chunk 3 kept that handler, only its allowed backend list
  needs widening from `("claude_cli", "api")` to include `"local"` and
  `"openai_compat"` — a one-line change, included in the plan).

## Testing

`tests/generate/providers/test_claude_cli.py`,
`test_claude_api.py` (both moved/adapted from existing `generate/
generator.py` tests), `test_openai_compatible.py` (mocks `httpx`, covers
the tool-call response parsing and both `local`/`openai_compat`
registrations), `test_registry.py`.
