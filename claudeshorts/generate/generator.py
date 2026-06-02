"""Generation of a single structured post.

Two backends, selected by ``model.backend`` in settings.yaml:

- ``claude_cli`` (default): shells out to the ``claude`` CLI in headless print
  mode. This runs under your **Claude Pro/Max subscription** auth (no metered
  API key needed) — the cheap path. The desktop must have Claude Code installed
  and logged in (`claude login`).
- ``api``: direct Anthropic SDK call with forced tool use (needs
  ``ANTHROPIC_API_KEY``). Uses prompt caching.

Both validate against ``schema.validate_post`` before returning. The model call
is isolated here so the rest of the pipeline can run with a mock generator.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Callable

from ..config import settings
from .schema import POST_TOOL, validate_post

# Static, prompt-cached (api backend). Defines voice + editorial rules.
SYSTEM_PROMPT = """\
You are the editorial engine for a daily tech/AI news account that publishes
short vertical videos (slideshows) to YouTube Shorts, TikTok, and Instagram
Reels. The account is the "newsletter": punchy, accurate, hype-free.

For each news item you receive, produce ONE post.

Rules:
- Voice: clear, energetic, factual. No clickbait, no fabricated facts. Only use
  information present in the item; never invent quotes, numbers, or outcomes.
- Slides: 3-7 of them. Slide 1 is the hook. Each slide has a short headline
  (<= 8 words) and up to 3 tight bullets. Include a one-line `voiceover` (spoken
  narration) and a `visual_hint` (what to show) per slide. Last slide is a brief
  takeaway / call to follow.
- thread_slug: a stable kebab-case id for the storyline (e.g. 'gpt-5-launch').
  If PRIOR COVERAGE is provided, REUSE its storyline: open slide 1 with a quick
  "Update:" recap, then focus the rest on what is new. Keep the same slug.
- theme: choose a color palette that matches the SUBJECT of the news (the
  company / product / topic), NOT the channel. Examples: Nvidia -> green
  (#76B900) on near-black; Anthropic -> clay/orange (#D97757) on warm gray;
  OpenAI -> teal/white on black; Apple -> silver on space-gray; Google ->
  blue (#4285F4) on white; Bitcoin/crypto -> orange (#F7931A) on black;
  generic AI research -> indigo on slate. Pick hex colors with strong contrast
  that read well on a vertical phone video, and set mood (dark|light) to match.
- Captions: tailor per platform. YouTube needs a title + 1-2 line description.
  TikTok and Instagram need a short caption. Provide 3-6 relevant hashtags each.
- Attribute the source naturally where it fits.
"""

GenerateFn = Callable[[dict, "str | None"], dict]


# --- prompt building -------------------------------------------------------
def build_user_prompt(item: dict, prior_coverage: str | None = None) -> str:
    parts = [
        "NEWS ITEM",
        f"Source: {item.get('source')}",
        f"Title: {item.get('title')}",
        f"URL: {item.get('url') or '(none)'}",
        f"Summary: {item.get('summary') or '(none)'}",
    ]
    if prior_coverage:
        parts += [
            "",
            "PRIOR COVERAGE (this is a FOLLOW-UP — recap briefly on slide 1, then "
            "cover only what is new; reuse the same thread_slug):",
            prior_coverage,
        ]
    return "\n".join(parts)


def build_cli_prompt(item: dict, prior_coverage: str | None = None) -> str:
    schema = json.dumps(POST_TOOL["input_schema"])
    return (
        SYSTEM_PROMPT
        + "\n\n"
        + build_user_prompt(item, prior_coverage)
        + "\n\nRespond with ONLY a single minified JSON object (no prose, no "
        "markdown code fences) that conforms to this JSON Schema:\n"
        + schema
    )


# --- claude_cli backend (subscription auth) --------------------------------
def _run_claude_cli(prompt: str, model: str, timeout: int) -> str:
    binary = shutil.which("claude") or "claude"
    try:
        proc = subprocess.run(
            [binary, "-p", "--output-format", "json", "--model", model],
            input=prompt, capture_output=True, text=True, timeout=timeout,
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


def _result_text(raw: str) -> str:
    """Pull the assistant text out of the `--output-format json` output.

    The CLI emits one of two shapes depending on version:
    - older: a single envelope ``{"type":"result","result":"..."}``;
    - Claude Code 2.1+: a JSON array of stream events whose final
      ``{"type":"result"}`` element carries the text.
    Falls back to assistant text blocks, then the raw string.
    """
    try:
        env = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    events = env if isinstance(env, list) else [env]
    # Prefer the terminal result event (last one wins).
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
    # Backward-compat: a bare dict envelope with a result string.
    if isinstance(env, dict) and isinstance(env.get("result"), str):
        return env["result"]
    # Fallback: concatenate assistant text blocks from a stream array.
    texts = [
        block.get("text", "")
        for e in events if isinstance(e, dict) and e.get("type") == "assistant"
        for block in (e.get("message", {}).get("content") or [])
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    if texts:
        return "\n".join(texts)
    return raw


def _parse_json_object(text: str) -> dict:
    """Tolerant extraction of the first {...} JSON object from model output."""
    s = (text or "").strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in Claude output")
    return json.loads(s[start:end + 1])


def _generate_via_cli(item: dict, prior: str | None, cfg: dict) -> dict:
    raw = _run_claude_cli(
        build_cli_prompt(item, prior),
        cfg.get("cli_model", "sonnet"),
        cfg.get("timeout_seconds", 180),
    )
    return _parse_json_object(_result_text(raw))


# --- api backend (metered key) ---------------------------------------------
def _make_client():
    from anthropic import Anthropic  # lazy: offline/CLI paths don't need it

    return Anthropic()


def _extract_tool_input(message: Any) -> dict:
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_post":
            return block.input
    raise ValueError("Claude response contained no emit_post tool_use block")


def _generate_via_api(item: dict, prior: str | None, cfg: dict,
                      client: Any | None, model: str | None) -> dict:
    model = model or cfg.get("name", "claude-sonnet-4-6")
    client = client or _make_client()
    if cfg.get("prompt_cache", True):
        system: Any = [{
            "type": "text", "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }]
    else:
        system = SYSTEM_PROMPT
    message = client.messages.create(
        model=model,
        max_tokens=cfg.get("max_tokens", 4096),
        system=system,
        tools=[POST_TOOL],
        tool_choice={"type": "tool", "name": "emit_post"},
        messages=[{"role": "user", "content": build_user_prompt(item, prior)}],
    )
    return _extract_tool_input(message)


# --- public entrypoint -----------------------------------------------------
def generate_post(
    item: dict,
    prior_coverage: str | None = None,
    *,
    client: Any | None = None,
    model: str | None = None,
    backend: str | None = None,
) -> dict:
    """Generate one validated structured post via the configured backend."""
    cfg = settings().get("model", {})
    backend = backend or cfg.get("backend", "claude_cli")

    if backend == "claude_cli":
        data = _generate_via_cli(item, prior_coverage, cfg)
    elif backend == "api":
        data = _generate_via_api(item, prior_coverage, cfg, client, model)
    else:
        raise ValueError(f"unknown model.backend: {backend!r} (use claude_cli|api)")

    errors = validate_post(data)
    if errors:
        raise ValueError("invalid post from Claude: " + "; ".join(errors))
    return data
