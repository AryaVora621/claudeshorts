"""Generation of a single structured post.

Backend selected by ``model.backend`` in settings.yaml (``claude_cli``,
``api``, ``local``, or ``openai_compat`` — see ``providers/registry.py`` for
what each one does). All backends validate against ``schema.validate_post``
before returning. The model call is isolated here so the rest of the
pipeline can run with a mock generator.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from ..config import settings
from . import schema
from .providers import registry

# Static, prompt-cached (api backend). Structural/editorial rules only —
# profile-specific voice/tone lives in config/profiles/<slug>/prompt.md and
# is threaded in by the caller (wired in a later task in this plan).
SYSTEM_PROMPT = """\
You are the editorial engine for a daily technology news account that publishes
short vertical videos (slideshows) to YouTube Shorts, TikTok, and Instagram
Reels. You cover the whole tech landscape: AI/ML, big-tech companies (OpenAI,
Google, Anthropic, Nvidia, AMD, Apple, Microsoft, Meta, Amazon, and others),
cybersecurity, hardware and chips, consumer gadgets, gaming, and science. The
account is the "newsletter": punchy, accurate, hype-free.

For each news item you receive, produce ONE post.

Rules:
- Only use information present in the item; never invent quotes, numbers, or
  outcomes.
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
    tool_schema = json.dumps(schema.POST_TOOL["input_schema"])
    return (
        SYSTEM_PROMPT
        + "\n\n"
        + build_user_prompt(item, prior_coverage)
        + "\n\nRespond with ONLY a single minified JSON object (no prose, no "
        "markdown code fences) that conforms to this JSON Schema:\n"
        + tool_schema
    )


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
    prompt = (
        build_cli_prompt(item, prior_coverage)
        if backend == "claude_cli"
        else build_user_prompt(item, prior_coverage)
    )
    provider = registry.get_provider(backend, client=client, model=model)
    data = provider.generate_structured(
        SYSTEM_PROMPT, prompt, schema.POST_TOOL, "emit_post",
    )
    errors = schema.validate_post(data)
    if errors:
        raise ValueError("invalid post from model: " + "; ".join(errors))
    return data
