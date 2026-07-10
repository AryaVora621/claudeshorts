# Chunk 12: Telegram bot interface

## Context

Twelfth of 14 chunks rebuilding claudeshorts per `goal.md`. This is a
deferred, human-required chunk (needs a real Telegram bot token from
BotFather). goal.md declares Telegram "a first-class interface" that must
call existing services and never duplicate logic, supporting: generate
videos, view queue, approve/reject uploads, retry failed jobs, manage
profiles, monitor workers, receive notifications, review logs.

## Current state

Chunk 4 already exposes every action the bot needs over
`/api/v1/*` (posts, articles, pipeline, jobs) — `services/posts_service.py`
etc. (chunk 3) remains the single implementation everything calls through.
There is no `/api/v1/profiles` endpoint yet (chunk 11's browser profiles
postdate chunk 4's REST API design) and no explicit "retry a failed job"
endpoint (chunk 2 only exposes cancel/pause/resume plus its own automatic
backoff-retry). Both are small, justified additions to the REST API layer
in this chunk rather than logic duplicated inside the bot.

## Decision (confirmed with user)

The bot is an **HTTP client of `/api/v1/*`**, matching goal.md's Frontend
Independence diagram (Telegram -> Backend API -> Publishing Service)
exactly — it never imports `claudeshorts.services` or `claudeshorts.store`
directly, only `httpx` calls against the already-running dashboard/API
process. It runs as its own standalone long-polling process (not inside
the FastAPI app's event loop) — simplest to reason about, and long-polling
needs no public URL/webhook, which fits a Raspberry Pi behind home NAT.

Scope, per the user's confirmed answer:
- **Single admin chat.** One `TELEGRAM_CHAT_ID` env var receives every
  notification; the bot also only responds to messages from that chat id
  (a minimal allowlist of one), rejecting anything else — this is a
  security boundary, not just a routing convenience, since the bot can
  trigger real pipeline/publish actions.
- **Profiles are view-only.** `/profiles` lists `slug`/`platform`/
  `login_health`; there is no Telegram command to perform a login —
  chunk 11's `interactive_login.py` needs a visible browser on the host
  machine and cannot run remotely from a chat command.

## Architecture

### Two small REST API additions (chunk 4 extension)

- `claudeshorts/api/profiles.py` — `GET /api/v1/profiles` -> `[{"slug":
  ..., "platform": ..., "login_health": ...}, ...]`, backed by chunk 11's
  `browser.profiles.list_profiles()`. Read-only, matching the bot's
  view-only profile scope.
- `claudeshorts/api/jobs.py` gains `POST /api/v1/jobs/{id}/retry` —
  re-enqueues a `FAILED` job with the same `job_type`/`payload` via
  `jobs.queue.enqueue`, returning the new job's id. This is a thin
  adapter over chunk 2's existing `enqueue`, not new business logic — it
  fills a real gap (goal.md explicitly lists "retry failed jobs" as a
  required Telegram capability, and no endpoint currently supports it).

### `claudeshorts/telegram_bot/` (new package)

- `client.py` — `ApiClient(base_url: str)`, thin `httpx`-based wrapper
  with one method per endpoint the bot calls (`generate(count)`,
  `list_posts(status)`, `approve(post_id)`, `reject(post_id, note)`,
  `list_jobs(status=None)`, `get_job(job_id)`, `retry_job(job_id)`,
  `list_profiles()`) — every method is a direct 1:1 HTTP call, no branching
  logic beyond building the request and returning parsed JSON.
- `bot.py` — the actual Telegram command handlers (built on
  `python-telegram-bot`'s `ApplicationBuilder`, long-polling), each handler
  doing: parse command args -> call one `ApiClient` method -> format a
  Telegram-friendly text reply. No handler contains business logic beyond
  text formatting.
- `notify.py` — `send_notification(text: str) -> None`, a fire-and-forget
  `httpx.post` to Telegram's `sendMessage` API using `TELEGRAM_BOT_TOKEN`/
  `TELEGRAM_CHAT_ID` — called from chunk 2's `jobs/worker.py` on job
  completion/failure and from chunk 5's scheduler after the weekly report
  runs. This is the "receive notifications" requirement; it's a push, not
  a bot command, so it lives in its own tiny module the worker/scheduler
  import directly (not an HTTP round-trip back through the API, since it
  originates from the same process as the job system).
- `__main__.py` — `python -m claudeshorts.telegram_bot` entry point,
  starting the polling loop. Reads `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`/
  `CLAUDESHORTS_API_BASE_URL` (default `http://127.0.0.1:8000`) from env.

### Command surface (mapped to goal.md's required capabilities)

| Command | Capability | Calls |
|---|---|---|
| `/generate [n]` | generate videos | `POST /pipeline/generate`, then polls `GET /jobs/{id}` up to a bounded number of times and replies with the final status |
| `/queue` | view queue | `GET /posts?status=rendered` (posts awaiting review) |
| `/approve <id>` | approve uploads | `POST /posts/{id}/approve` |
| `/reject <id> [note]` | reject uploads | `POST /posts/{id}/reject` |
| `/retry <job_id>` | retry failed jobs | `POST /jobs/{id}/retry` |
| `/profiles` | manage profiles (view-only) | `GET /profiles` |
| `/workers` | monitor workers | `GET /jobs?status=running` |
| `/logs <job_id>` | review logs | `GET /jobs/{id}` (its `log` field, chunk 2's existing column) |

Every row is a direct pass-through — no command computes anything the API
doesn't already return.

### Access control

`bot.py`'s top-level update handler checks `update.effective_chat.id ==
int(os.environ["TELEGRAM_CHAT_ID"])` before dispatching to any command
handler; a mismatched chat id gets a fixed "not authorized" reply and no
API call is made. This is intentionally simple (one allowlisted id, no
role system) matching the single-operator scope decision.

## Out of scope for this chunk

- Multi-user/team chat support (explicit user decision — single admin
  chat only for now).
- Any Telegram-driven profile *creation* or login — view-only, per the
  user's decision; `interactive_login.py` remains a host-machine-only
  script (chunk 11).
- Webhook-based delivery (vs. long-polling) — long-polling needs no
  public URL/TLS cert, which fits home-network/Raspberry Pi deployment
  better; revisit only if latency or scaling ever demands it.
- Inline keyboards / rich Telegram UI (buttons, callback queries) — plain
  text commands and replies are sufficient for the required capability
  list; richer UI is a polish item, not a functional gap.

## Testing

`tests/api/test_profiles_api.py` — `GET /profiles` returns
`browser.profiles.list_profiles()`'s shape (using a temp profile dir,
matching chunk 11's `test_profiles.py` fixture pattern).
`tests/api/test_jobs_retry.py` — `POST /jobs/{id}/retry` re-enqueues with
the same `job_type`/`payload`, returns 404 for a non-`FAILED` job (can't
retry a job that isn't failed) or a missing id.
`tests/telegram_bot/test_client.py` — `ApiClient`'s methods build the
correct request (URL, method, body) against a mocked `httpx` transport,
matching chunk 8/10's HTTP-mocking test pattern.
`tests/telegram_bot/test_bot.py` — command handlers call the right
`ApiClient` method and format the expected reply text, given a fake
`ApiClient`; the chat-id allowlist check rejects an unauthorized chat id
without calling the client at all.
Manual (documented, final human-required task): create a real bot via
BotFather, set `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, run
`python -m claudeshorts.telegram_bot`, and exercise `/queue`, `/generate
1`, `/approve <id>` against a real running dashboard process.
