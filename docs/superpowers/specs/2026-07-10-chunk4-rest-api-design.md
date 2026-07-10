# Chunk 4: REST API over services

## Context

Fourth of 14 chunks rebuilding claudeshorts per `goal.md` (see `TASK_QUEUE.md`
/ session task list). goal.md lists REST API as a first-class interface
alongside CLI/dashboard/Telegram/Discord, all calling shared services —
"the backend must never depend on the existence of any frontend." Chunk 3
made `claudeshorts/services/` the single implementation of every
user-facing action; this chunk exposes those same functions over HTTP so
chunk 12 (Telegram bot) and any future client have something to call
without duplicating dashboard route logic.

## Decisions (confirmed with user)

1. **One process, not two.** The API is mounted under `/api/v1/*` in the
   same FastAPI app the dashboard already runs (`claudeshorts/dashboard/
   app.py`'s `create_app()`), not a separate server. Simplest to deploy on
   a Raspberry Pi — one process, one port, one `uvicorn` invocation from
   `cli.py serve`.
2. **No authentication for now.** Matches the dashboard's current posture
   (LAN-accessible, no login) — this project runs at single-operator scale
   on a home network. Revisit if/when the API is ever exposed beyond the
   LAN.
3. **Slow actions are async; fast actions are sync.** Ingest/generate/
   render/full-run go through the chunk-2 job queue and return `202
   Accepted` + a job id immediately. Post/article actions (approve, reject,
   schedule, pin, unpin, add) are fast enough to run synchronously and
   return the service function's result dict as JSON with `200 OK` (or
   `404`/`409` for the same failure cases the dashboard already handles).

## Architecture

### Router layout

New `claudeshorts/api/` package, mounted onto the existing app:

- `claudeshorts/api/__init__.py` — `router = APIRouter(prefix="/api/v1")`
  aggregating the sub-routers below; `dashboard/app.py`'s `create_app()`
  gains one line: `app.include_router(api.router)`.
- `claudeshorts/api/posts.py` — `POST /posts/{id}/approve`, `POST
  /posts/{id}/reject`, `POST /posts/{id}/schedule`, `POST
  /posts/{id}/export`, `GET /posts/{id}`, `GET /posts`.
- `claudeshorts/api/articles.py` — `POST /articles`, `POST
  /articles/{id}/pin`, `POST /articles/{id}/unpin`, `POST
  /articles/{id}/generate`, `GET /articles`.
- `claudeshorts/api/pipeline.py` — `POST /pipeline/ingest`, `POST
  /pipeline/generate`, `POST /pipeline/render/{post_id}`, `POST
  /pipeline/run` — each enqueues via `claudeshorts.jobs.queue.enqueue` and
  returns `{"job_id": int}` with status 202.
- `claudeshorts/api/jobs.py` — `GET /jobs/{id}`, `GET /jobs`, `POST
  /jobs/{id}/cancel`, `POST /jobs/{id}/pause`, `POST /jobs/{id}/resume`.
- `claudeshorts/api/health.py` — `GET /health` → `{"status": "ok"}`, the
  one route reachable without any future auth layer, for uptime checks.

Every route handler is a thin adapter: parse the request body (Pydantic
model) or path param, call exactly one `services.*` function (or
`jobs.queue.*` for enqueue/cancel/pause/resume — chunk 2's own layer, not
duplicated here), map exceptions to HTTP status codes
(`ValueError → 404`, `FileNotFoundError → 409`), return the result as JSON.
No business logic in `claudeshorts/api/*.py`, matching the same rule chunk
3 applied to the dashboard.

### Request/response models

Pydantic models in `claudeshorts/api/schemas.py`:

```python
class ApproveResponse(BaseModel):
    post_id: int
    exported: bool
    scheduled_for: str | None

class ScheduleRequest(BaseModel):
    scheduled_for: str | None = None

class RejectRequest(BaseModel):
    note: str | None = None

class AddArticleRequest(BaseModel):
    title: str
    url: str | None = None
    summary: str | None = None
    action: str = "pin"

class EnqueueResponse(BaseModel):
    job_id: int

class JobResponse(BaseModel):
    id: int
    name: str
    status: str
    job_type: str
    attempts: int
    error: str | None
```

(Exact field set for `JobResponse` finalized in the plan against chunk 2's
`jobs` table columns.)

### Error mapping

A small shared helper in `claudeshorts/api/errors.py`:

```python
def service_call(fn, *args, **kwargs):
    """Call a services.* function, translating its exceptions to HTTPException."""
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(409, str(exc))
```

Used by every route handler so the exception-to-status mapping lives in
one place instead of being repeated per route.

## Out of scope for this chunk

- Authentication/authorization (explicit user decision, deferred).
- Rate limiting, request logging beyond what chunk 6 (structured logging)
  will add generally.
- Any new business logic — this chunk is a pure HTTP adapter over chunk 3's
  services and chunk 2's job queue, same as the dashboard is.
- OpenAPI/Swagger customization beyond FastAPI's automatic docs (already
  free from using FastAPI + Pydantic models — no extra work needed to get
  `/docs`).

## Testing

`tests/api/test_posts_api.py`, `test_articles_api.py`,
`test_pipeline_api.py`, `test_jobs_api.py` using FastAPI's `TestClient`
against `create_app()`, asserting status codes and response bodies for
both success and the `ValueError`/`FileNotFoundError` mapped-error cases.
