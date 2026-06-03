# PLAN — local model generation backend (Qwen on the P40 desktop)

Status: PLANNING (not started). Goal is a third generation backend so posts can
be written by a local LLM on the home server's Nvidia P40 instead of the metered
Anthropic API or the `claude` CLI subscription. Slower, but effectively free.

## Why
Generation is the only step that calls a model. Today `model.backend` is
`claude_cli` (subscription) or `api` (metered key). A `local` backend lets the
desktop generate posts with no per-call cost. Everything downstream (render,
review, carousel, endslide, publish) is unchanged.

## Hardware reality check (READ FIRST)
The P40 is **Pascal** (GP102, compute capability 6.1, 24 GB GDDR5). Two
consequences that change the plan:

- **fp8 is not an option on a P40.** fp8 inference (e.g. vLLM FP8) needs
  Ada/Hopper (cc 8.9+). Pascal has no fp8 and no usable bf16; even fp16 throughput
  is crippled (1:64 vs fp32 on GP102). So "qwen 30b fp8" cannot run as fp8 here.
- **The practical path is integer-quantized GGUF** via llama.cpp / Ollama, which
  runs fine on Pascal. Plan around GGUF Q4/Q5, not fp8.

A "30B" Qwen at fp16 is ~60 GB and will not fit in 24 GB regardless, so some
quantization is required no matter what.

## Model choice
- Recommended: **Qwen3-30B-A3B** (MoE, ~3B active params) in **GGUF Q4_K_M**
  (~18-19 GB) — fits in 24 GB with room for a few-thousand-token context, and the
  MoE keeps it reasonably fast despite the older card. Q5_K_M if it fits with the
  context we need.
- Fallback if VRAM/quality is tight: a dense ~14B (Qwen2.5-14B-Instruct) at
  Q4/Q5, which is smaller and a known-good instruction follower.

## Inference server
Pick one that exposes an **OpenAI-compatible** `/v1/chat/completions` so the
Python side stays simple and provider-neutral.

- **Ollama** (recommended to start): easiest to install/run on Linux, pulls GGUF,
  OpenAI-compatible endpoint, survives reboots as a service. Good enough perf.
- **llama.cpp `llama-server`**: more control; crucially supports **GBNF grammar**
  so we can FORCE output to match our JSON schema (big reliability win on a
  smaller model). Use this if Ollama's JSON adherence is shaky.
- **vLLM**: skip. Pascal support is poor and there is no fp8 path here.

## Integration design (Python)
Add a third branch in `generate/generator.py::generate_post` alongside
`claude_cli` / `api`:

- New backend id `local` (or `openai_compat`).
- Reuse the existing **JSON-in-prompt** approach already used by the CLI backend
  (`build_cli_prompt` asks for one minified JSON object matching `POST_TOOL`'s
  schema) and the tolerant `_parse_json_object` + `validate_post`. Do NOT rely on
  the model's tool-calling; local 30B tool-calling is unreliable, and we already
  have a robust JSON-parse + validate path.
- Talk to the server over its OpenAI-compatible Chat Completions API via `httpx`
  (already a dependency). No new SDK needed. No API key (send a dummy if the
  server insists).
- Reliability levers, in order of preference:
  1. llama.cpp **GBNF grammar** generated from `POST_TOOL["input_schema"]` to
     guarantee structurally valid JSON.
  2. Server-side **JSON mode** (`response_format: {type: json_object}`) if the
     server supports it.
  3. Bounded **retries** on `validate_post` failure (the batch runner already
     isolates a single post's failure, so a bad item is skipped, not fatal).

## Config (settings.yaml `model`)
```yaml
model:
  backend: local            # claude_cli | api | local
  local:
    base_url: http://127.0.0.1:11434/v1   # Ollama default (server runs on the desktop)
    model: qwen3-30b-a3b                   # whatever the server registers it as
    timeout_seconds: 600                   # P40 is slow; be generous
    temperature: 0.7
    json_mode: true                        # or grammar, depending on server
```
No `.env` secret needed. The dashboard Settings page can later gain a "local"
option mirroring the existing backend switch.

## Verification plan (once the desktop is reachable again)
1. On the desktop: install the server, pull the GGUF, confirm
   `curl $base_url/models` and a trivial chat completion work.
2. Point a `local` backend at it; run `cli generate --limit 1` on one item;
   confirm `validate_post` passes and the JSON is well-formed.
3. Eyeball quality vs a Claude-generated post (voice, no em dashes, slide
   structure). Tune temperature / prompt / quant as needed.
4. Measure tokens/sec and a full single-post wall time to set realistic batch
   expectations.

## Open decisions (need a call)
- Server: start with **Ollama** (easiest) and only move to llama.cpp if JSON
  adherence is poor? (Recommended.)
- Acceptable quality bar vs Claude: is "good enough, free, slower" the trade we
  want for daily posts, or keep Claude for the hook slide and use local for the
  rest? (Hybrid is possible later.)
- Quant target: Q4_K_M (safe fit) vs Q5_K_M (better quality, tighter VRAM)?

## Out of scope (for now)
TTS/voice, image generation, or running the renderer on the GPU. This plan is
only the text-generation backend.
