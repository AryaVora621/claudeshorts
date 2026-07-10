# Chunk 4: REST API Over Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mount a `/api/v1/*` REST API in the same FastAPI process as the dashboard, exposing chunk 3's `services/*` and chunk 2's job queue as thin JSON endpoints — no auth (matches the dashboard's current LAN-only posture), no new business logic.

**Architecture:** New `claudeshorts/api/` package with one router module per domain (`posts.py`, `articles.py`, `pipeline.py`, `jobs.py`, `health.py`), a shared `errors.py` helper mapping `ValueError`/`FileNotFoundError` to HTTP status codes, and Pydantic request/response models in `schemas.py`. `dashboard/app.py`'s `create_app()` gains one `include_router` call.

**Tech Stack:** FastAPI (existing dependency), Pydantic (bundled with FastAPI).

## Global Constraints

- Python 3.11+, type hints everywhere, PEP 8.
- No comments explaining *what*, only non-obvious *why*.
- No auth on any route in this chunk (explicit user decision).
- Every route handler calls exactly one `services.*` (or `jobs.queue.*`) function — no business logic in `claudeshorts/api/*.py`.
- Full spec: `docs/superpowers/specs/2026-07-10-chunk4-rest-api-design.md`.

---

## File Structure

- Create: `claudeshorts/api/__init__.py`, `schemas.py`, `errors.py`, `health.py`, `posts.py`, `articles.py`, `pipeline.py`, `jobs.py`
- Modify: `claudeshorts/dashboard/app.py` — mount the router
- Create: `tests/api/test_health_api.py`, `test_posts_api.py`, `test_articles_api.py`, `test_pipeline_api.py`, `test_jobs_api.py`

---

### Task 1: `errors.py` + `health.py` + package skeleton

**Files:**
- Create: `claudeshorts/api/__init__.py`
- Create: `claudeshorts/api/errors.py`
- Create: `claudeshorts/api/health.py`
- Test: `tests/api/test_health_api.py`

**Interfaces:**
- Produces: `service_call(fn, *args, **kwargs) -> Any` (raises `HTTPException`), `router: APIRouter` (aggregator, empty until later tasks add sub-routers).

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_health_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app


def test_health_returns_ok():
    client = TestClient(create_app())
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_health_api.py -v`
Expected: FAIL — 404 (route doesn't exist yet)

- [ ] **Step 3: Implement the package skeleton**

```python
# claudeshorts/api/errors.py
"""Maps services.* exceptions to HTTP status codes, in one place, so every
route handler stays a one-line adapter instead of repeating try/except."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from fastapi import HTTPException

T = TypeVar("T")


def service_call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(409, str(exc)) from exc
```

```python
# claudeshorts/api/health.py
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

```python
# claudeshorts/api/__init__.py
"""REST API over claudeshorts services (goal.md: backend never depends on
any frontend — this is one more client of `services/`, same as the CLI and
dashboard)."""

from __future__ import annotations

from fastapi import APIRouter

from . import health

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
```

- [ ] **Step 4: Mount the router in `dashboard/app.py`**

In `claudeshorts/dashboard/app.py`, add near the top-level imports:
```python
from .. import api
```

In `create_app()`, right after `app.mount("/static", ...)`, add:
```python
    app.include_router(api.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/api/test_health_api.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/api/__init__.py claudeshorts/api/errors.py claudeshorts/api/health.py claudeshorts/dashboard/app.py tests/api/test_health_api.py
git commit -m "feat: add REST API skeleton mounted at /api/v1, health endpoint"
```

---

### Task 2: `schemas.py` + `posts.py` router

**Files:**
- Create: `claudeshorts/api/schemas.py`
- Create: `claudeshorts/api/posts.py`
- Modify: `claudeshorts/api/__init__.py`
- Test: `tests/api/test_posts_api.py`

**Interfaces:**
- Consumes: `services.posts_service.*`, `store.{connect, get_post, all_posts}`
- Produces: `GET /api/v1/posts`, `GET /api/v1/posts/{id}`, `POST /api/v1/posts/{id}/approve`, `POST /api/v1/posts/{id}/reject`, `POST /api/v1/posts/{id}/schedule`, `POST /api/v1/posts/{id}/export`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_posts_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app
from claudeshorts.store import connect, posts


def _mk_post():
    with connect() as conn:
        return posts.insert_post(conn, item_ids=[1], title="T", slides={}, captions={})


def test_get_post_not_found():
    client = TestClient(create_app())
    resp = client.get("/api/v1/posts/999999")
    assert resp.status_code == 404


def test_get_post_found():
    client = TestClient(create_app())
    post_id = _mk_post()
    resp = client.get(f"/api/v1/posts/{post_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == post_id


def test_list_posts():
    client = TestClient(create_app())
    _mk_post()
    resp = client.get("/api/v1/posts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_approve_post(monkeypatch):
    client = TestClient(create_app())
    post_id = _mk_post()
    from claudeshorts.services import posts_service
    monkeypatch.setattr(posts_service, "export_post", lambda post: [])
    resp = client.post(f"/api/v1/posts/{post_id}/approve")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"post_id": post_id, "exported": True, "scheduled_for": None}


def test_approve_post_not_found():
    client = TestClient(create_app())
    resp = client.post("/api/v1/posts/999999/approve")
    assert resp.status_code == 404


def test_reject_post_with_note():
    client = TestClient(create_app())
    post_id = _mk_post()
    resp = client.post(f"/api/v1/posts/{post_id}/reject", json={"note": "meh"})
    assert resp.status_code == 200
    assert resp.json() == {"post_id": post_id}


def test_schedule_post():
    client = TestClient(create_app())
    post_id = _mk_post()
    resp = client.post(f"/api/v1/posts/{post_id}/schedule", json={"scheduled_for": "2099-01-01"})
    assert resp.status_code == 200
    assert resp.json() == {"post_id": post_id, "scheduled_for": "2099-01-01"}


def test_export_post_not_found():
    client = TestClient(create_app())
    resp = client.post("/api/v1/posts/999999/export")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_posts_api.py -v`
Expected: FAIL — 404 for all (routes don't exist)

- [ ] **Step 3: Implement `schemas.py`**

```python
# claudeshorts/api/schemas.py
"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from pydantic import BaseModel


class ApproveResponse(BaseModel):
    post_id: int
    exported: bool
    scheduled_for: str | None


class ScheduleRequest(BaseModel):
    scheduled_for: str | None = None


class ScheduleResponse(BaseModel):
    post_id: int
    scheduled_for: str | None


class RejectRequest(BaseModel):
    note: str | None = None


class PostIdResponse(BaseModel):
    post_id: int


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

- [ ] **Step 4: Implement `posts.py`**

```python
# claudeshorts/api/posts.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..services import posts_service
from ..store import all_posts, connect, get_post
from .errors import service_call
from .schemas import ApproveResponse, PostIdResponse, RejectRequest, ScheduleRequest, ScheduleResponse

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("")
def list_posts(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        return all_posts(conn, limit)


@router.get("/{post_id}")
def get_post_route(post_id: int) -> dict[str, Any]:
    with connect() as conn:
        post = get_post(conn, post_id)
    if not post:
        raise HTTPException(404, f"post {post_id} not found")
    return post


@router.post("/{post_id}/approve", response_model=ApproveResponse)
def approve(post_id: int) -> dict[str, Any]:
    return service_call(posts_service.approve_post, post_id)


@router.post("/{post_id}/reject", response_model=PostIdResponse)
def reject(post_id: int, body: RejectRequest) -> dict[str, Any]:
    return service_call(posts_service.reject_post, post_id, note=body.note)


@router.post("/{post_id}/schedule", response_model=ScheduleResponse)
def schedule(post_id: int, body: ScheduleRequest) -> dict[str, Any]:
    return service_call(posts_service.schedule_post, post_id, body.scheduled_for)


@router.post("/{post_id}/export", response_model=PostIdResponse)
def export_now(post_id: int) -> dict[str, Any]:
    return service_call(posts_service.export_post_now, post_id)
```

- [ ] **Step 5: Register the router in `claudeshorts/api/__init__.py`**

```python
from . import health, posts

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(posts.router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/api/test_posts_api.py -v`
Expected: PASS (8 tests)

- [ ] **Step 7: Commit**

```bash
git add claudeshorts/api/schemas.py claudeshorts/api/posts.py claudeshorts/api/__init__.py tests/api/test_posts_api.py
git commit -m "feat: add REST API posts router (approve/reject/schedule/export)"
```

---

### Task 3: `articles.py` router

**Files:**
- Create: `claudeshorts/api/articles.py`
- Modify: `claudeshorts/api/__init__.py`
- Test: `tests/api/test_articles_api.py`

**Interfaces:**
- Consumes: `services.articles_service.*`, `store.{connect, latest_items}`
- Produces: `GET /api/v1/articles`, `POST /api/v1/articles`, `POST /api/v1/articles/{id}/pin`, `POST /api/v1/articles/{id}/unpin`, `POST /api/v1/articles/{id}/generate`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_articles_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app


def test_add_article_pins_by_default():
    client = TestClient(create_app())
    resp = client.post("/api/v1/articles", json={"title": "Hello API"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert "job_id" not in body


def test_add_article_generate_action_returns_job_id():
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/articles", json={"title": "Hello API 2", "action": "generate"}
    )
    assert resp.status_code == 200
    assert "job_id" in resp.json()


def test_add_article_missing_title_is_422():
    client = TestClient(create_app())
    resp = client.post("/api/v1/articles", json={})
    assert resp.status_code == 422


def test_pin_unpin_article():
    client = TestClient(create_app())
    add = client.post("/api/v1/articles", json={"title": "Pin via API"}).json()
    item_id = add["item_id"]
    resp = client.post(f"/api/v1/articles/{item_id}/unpin")
    assert resp.status_code == 200
    resp = client.post(f"/api/v1/articles/{item_id}/pin")
    assert resp.status_code == 200


def test_generate_from_item_returns_job_id():
    client = TestClient(create_app())
    add = client.post("/api/v1/articles", json={"title": "Gen via API"}).json()
    resp = client.post(f"/api/v1/articles/{add['item_id']}/generate")
    assert resp.status_code == 200
    assert isinstance(resp.json()["job_id"], int)


def test_list_articles():
    client = TestClient(create_app())
    resp = client.get("/api/v1/articles")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_articles_api.py -v`
Expected: FAIL — 404 (routes don't exist)

- [ ] **Step 3: Implement `articles.py`**

```python
# claudeshorts/api/articles.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..services import articles_service
from ..store import connect, latest_items
from .schemas import AddArticleRequest, EnqueueResponse

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("")
def list_articles(limit: int = 120) -> list[dict[str, Any]]:
    with connect() as conn:
        return latest_items(conn, limit)


@router.post("")
def add_article(body: AddArticleRequest) -> dict[str, Any]:
    return articles_service.add_manual_article(
        title=body.title, url=body.url, summary=body.summary, action=body.action,
    )


@router.post("/{item_id}/pin")
def pin(item_id: int) -> dict[str, Any]:
    return articles_service.pin_article(item_id)


@router.post("/{item_id}/unpin")
def unpin(item_id: int) -> dict[str, Any]:
    return articles_service.unpin_article(item_id)


@router.post("/{item_id}/generate", response_model=EnqueueResponse)
def generate(item_id: int) -> dict[str, Any]:
    return articles_service.generate_from_item(item_id)
```

- [ ] **Step 4: Register the router**

In `claudeshorts/api/__init__.py`:
```python
from . import articles, health, posts

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(posts.router)
router.include_router(articles.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/api/test_articles_api.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/api/articles.py claudeshorts/api/__init__.py tests/api/test_articles_api.py
git commit -m "feat: add REST API articles router (add/pin/unpin/generate)"
```

---

### Task 4: `pipeline.py` router (async, job-queue-backed)

**Files:**
- Create: `claudeshorts/api/pipeline.py`
- Modify: `claudeshorts/api/__init__.py`
- Test: `tests/api/test_pipeline_api.py`

**Interfaces:**
- Consumes: `claudeshorts.jobs.queue.enqueue`
- Produces: `POST /api/v1/pipeline/ingest`, `POST /api/v1/pipeline/generate`, `POST /api/v1/pipeline/render/{post_id}`, `POST /api/v1/pipeline/run` — all return `202` + `{"job_id": int}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_pipeline_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app


def test_ingest_enqueues_job():
    client = TestClient(create_app())
    resp = client.post("/api/v1/pipeline/ingest")
    assert resp.status_code == 202
    assert isinstance(resp.json()["job_id"], int)


def test_generate_enqueues_job():
    client = TestClient(create_app())
    resp = client.post("/api/v1/pipeline/generate")
    assert resp.status_code == 202


def test_render_enqueues_job_with_post_id():
    client = TestClient(create_app())
    resp = client.post("/api/v1/pipeline/render/42")
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    from claudeshorts.store import connect, jobs as store_jobs
    with connect() as conn:
        row = store_jobs.get_job(conn, job_id)
    assert row["payload"] == {"post_id": 42}


def test_run_enqueues_full_run_job():
    client = TestClient(create_app())
    resp = client.post("/api/v1/pipeline/run")
    assert resp.status_code == 202
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_pipeline_api.py -v`
Expected: FAIL — 404 (routes don't exist)

- [ ] **Step 3: Implement `pipeline.py`**

```python
# claudeshorts/api/pipeline.py
from __future__ import annotations

from fastapi import APIRouter, status

from ..jobs import queue as job_queue
from .schemas import EnqueueResponse

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/ingest", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest() -> dict[str, int]:
    return {"job_id": job_queue.enqueue("ingest", {}, name="ingest (api)")}


@router.post("/generate", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def generate() -> dict[str, int]:
    return {"job_id": job_queue.enqueue("generate", {}, name="generate (api)")}


@router.post(
    "/render/{post_id}", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED,
)
def render(post_id: int) -> dict[str, int]:
    job_id = job_queue.enqueue(
        "render_post", {"post_id": post_id}, name=f"render post {post_id} (api)"
    )
    return {"job_id": job_id}


@router.post("/run", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def run() -> dict[str, int]:
    return {"job_id": job_queue.enqueue("full_run", {}, name="daily run (api)")}
```

- [ ] **Step 4: Register the router**

In `claudeshorts/api/__init__.py`:
```python
from . import articles, health, pipeline, posts

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(posts.router)
router.include_router(articles.router)
router.include_router(pipeline.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/api/test_pipeline_api.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/api/pipeline.py claudeshorts/api/__init__.py tests/api/test_pipeline_api.py
git commit -m "feat: add REST API pipeline router (async, job-queue-backed)"
```

---

### Task 5: `jobs.py` router

**Files:**
- Create: `claudeshorts/api/jobs.py`
- Modify: `claudeshorts/api/__init__.py`
- Test: `tests/api/test_jobs_api.py`

**Interfaces:**
- Consumes: `claudeshorts.store.jobs.{get_job, recent_jobs}`, `claudeshorts.jobs.queue.{request_cancel, request_pause, resume}`
- Produces: `GET /api/v1/jobs/{id}`, `GET /api/v1/jobs`, `POST /api/v1/jobs/{id}/cancel`, `POST /api/v1/jobs/{id}/pause`, `POST /api/v1/jobs/{id}/resume`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_jobs_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app
from claudeshorts.jobs import queue


def test_get_job_not_found():
    client = TestClient(create_app())
    resp = client.get("/api/v1/jobs/999999")
    assert resp.status_code == 404


def test_get_job_found():
    client = TestClient(create_app())
    job_id = queue.enqueue("ingest", {}, name="ingest")
    resp = client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id
    assert resp.json()["status"] == "PENDING"


def test_list_jobs():
    client = TestClient(create_app())
    queue.enqueue("ingest", {}, name="ingest")
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_cancel_job():
    client = TestClient(create_app())
    job_id = queue.enqueue("ingest", {}, name="ingest")
    resp = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "CANCELLED"


def test_pause_and_resume_job():
    client = TestClient(create_app())
    job_id = queue.enqueue("ingest", {}, name="ingest")
    client.post(f"/api/v1/jobs/{job_id}/pause")
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "PAUSED"
    client.post(f"/api/v1/jobs/{job_id}/resume")
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "PENDING"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_jobs_api.py -v`
Expected: FAIL — 404 (routes don't exist)

- [ ] **Step 3: Implement `jobs.py`**

```python
# claudeshorts/api/jobs.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..jobs import queue as job_queue
from ..store import connect
from ..store import jobs as store_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = store_jobs.get_job(conn, job_id)
    if not row:
        raise HTTPException(404, f"job {job_id} not found")
    return row


@router.get("")
def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        return store_jobs.recent_jobs(conn, limit)


@router.post("/{job_id}/cancel")
def cancel(job_id: int) -> dict[str, Any]:
    job_queue.request_cancel(job_id)
    return {"job_id": job_id}


@router.post("/{job_id}/pause")
def pause(job_id: int) -> dict[str, Any]:
    job_queue.request_pause(job_id)
    return {"job_id": job_id}


@router.post("/{job_id}/resume")
def resume(job_id: int) -> dict[str, Any]:
    job_queue.resume(job_id)
    return {"job_id": job_id}
```

- [ ] **Step 4: Register the router**

In `claudeshorts/api/__init__.py`:
```python
from . import articles, health, jobs, pipeline, posts

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(posts.router)
router.include_router(articles.router)
router.include_router(pipeline.router)
router.include_router(jobs.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/api/test_jobs_api.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Manual verification**

Run: `./start-dashboard.sh`, then in another terminal:
```bash
curl -s http://127.0.0.1:8000/api/v1/health
curl -s -X POST http://127.0.0.1:8000/api/v1/pipeline/ingest
curl -s http://127.0.0.1:8000/api/v1/jobs
```
Confirm valid JSON responses, and open `http://127.0.0.1:8000/docs` to
confirm FastAPI's automatic OpenAPI docs list every route added in this
chunk.

- [ ] **Step 7: Commit**

```bash
git add claudeshorts/api/jobs.py claudeshorts/api/__init__.py tests/api/test_jobs_api.py
git commit -m "feat: add REST API jobs router (status/list/cancel/pause/resume)"
```

---

### Task 6: Update checkpoint and task tracking

**Files:**
- Modify: `CHECKPOINT_LAST.md`, `TASK_QUEUE.md`

- [ ] **Step 1: Record completion**

Update `TASK_QUEUE.md` to move chunk 4 to Done. Update `CHECKPOINT_LAST.md`
with next action: chunk 5 (scheduling engine).

- [ ] **Step 2: Commit**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 4 complete — REST API live over services and job queue"
```

---

## Self-Review Notes

**Spec coverage:** All 5 router modules from the spec implemented
(health, posts, articles, pipeline, jobs). Async-vs-sync split matches the
spec exactly (pipeline enqueues + 202, posts/articles run sync + 200).
`errors.py`'s `service_call` centralizes exception mapping as specified.
No auth added anywhere, per the confirmed decision. FastAPI's automatic
`/docs` verified in Task 5 Step 6 rather than assumed.

**Placeholder scan:** none — every route has a real implementation calling
a real service function.

**Type consistency:** `PostIdResponse`/`ScheduleResponse`/`ApproveResponse`
field names match exactly what `services.posts_service.*` already returns
(verified against chunk 3's plan) — no remapping needed between service
dict and API response model. `EnqueueResponse.job_id` matches
`jobs.queue.enqueue`'s return type (`int`) used consistently across
`articles.py` and `pipeline.py`.
