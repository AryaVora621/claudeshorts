# Chunk 3: Service Layer Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract `claudeshorts/services/` (`posts_service.py`, `articles_service.py`, `pipeline_service.py`) so business logic currently inline in `dashboard/app.py` route handlers and `jobs/registry.py` lives in one reusable place, with CLI/dashboard/job-registry as thin callers and zero behavior change.

**Architecture:** Each service function wraps existing domain-package calls (`ingest.run_ingest`, `generate.run_generate`/`generate_for_item`, `render.render_post`, `publish.export_post`, `orchestrate.run_pipeline`) plus the store status-transition side effects a user action implies, returning plain dicts or raising the same exceptions already in use (`ValueError`, `FileNotFoundError`).

**Tech Stack:** Python 3.11+, no new dependencies.

## Global Constraints

- Python 3.11+, type hints everywhere, PEP 8.
- No comments explaining *what*, only non-obvious *why*.
- Zero behavior change: every route/CLI command must produce the same
  user-visible output after this chunk as before.
- Full spec: `docs/superpowers/specs/2026-07-10-chunk3-service-layer-design.md`.

---

## File Structure

- Create: `claudeshorts/services/__init__.py`, `posts_service.py`, `articles_service.py`, `pipeline_service.py`
- Modify: `claudeshorts/dashboard/app.py` — 9 route handlers become thin
- Modify: `claudeshorts/jobs/registry.py` — becomes a pure lookup table
- Modify: `claudeshorts/cli.py` — `ingest`/`generate`/`render`/`run` commands call services
- Create: `tests/services/test_posts_service.py`, `test_articles_service.py`, `test_pipeline_service.py`

---

### Task 1: `posts_service.py`

**Files:**
- Create: `claudeshorts/services/__init__.py` (empty)
- Create: `claudeshorts/services/posts_service.py`
- Test: `tests/services/test_posts_service.py`

**Interfaces:**
- Consumes: `claudeshorts.store.{connect, get_post, set_status, set_schedule}`, `claudeshorts.publish.export_post`
- Produces: `approve_post(post_id) -> dict`, `reject_post(post_id, note=None) -> dict`, `schedule_post(post_id, scheduled_for) -> dict`, `export_post_now(post_id) -> dict`. All raise `ValueError` if the post doesn't exist.

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_posts_service.py
from __future__ import annotations

import pytest

from claudeshorts.services import posts_service
from claudeshorts.store import connect, insert_post, set_schedule


def _mk_post(**overrides):
    kwargs = dict(item_ids=[1], title="T", slides={"a": 1}, captions={"b": 2})
    kwargs.update(overrides)
    with connect() as conn:
        return posts_service_test_insert(conn, kwargs)


def posts_service_test_insert(conn, kwargs):
    from claudeshorts.store import posts
    return posts.insert_post(conn, **kwargs)


def test_approve_post_not_found_raises():
    with pytest.raises(ValueError, match="not found"):
        posts_service.approve_post(999999)


def test_approve_post_without_schedule_exports_immediately(monkeypatch):
    post_id = _mk_post()
    called = {}

    def fake_export(post):
        called["post_id"] = post["id"]
        return []

    monkeypatch.setattr(posts_service, "export_post", fake_export)
    result = posts_service.approve_post(post_id)
    assert result == {"post_id": post_id, "exported": True, "scheduled_for": None}
    assert called["post_id"] == post_id
    with connect() as conn:
        from claudeshorts.store import get_post
        assert get_post(conn, post_id)["status"] == "approved"


def test_approve_post_with_schedule_does_not_export(monkeypatch):
    post_id = _mk_post()
    with connect() as conn:
        set_schedule(conn, post_id, "2099-01-01")
    monkeypatch.setattr(
        posts_service, "export_post",
        lambda post: (_ for _ in ()).throw(AssertionError("should not export")),
    )
    result = posts_service.approve_post(post_id)
    assert result == {"post_id": post_id, "exported": False, "scheduled_for": "2099-01-01"}


def test_reject_post_sets_status_and_note():
    post_id = _mk_post()
    posts_service.reject_post(post_id, note="not good enough")
    with connect() as conn:
        from claudeshorts.store import get_post
        got = get_post(conn, post_id)
    assert got["status"] == "rejected"
    assert got["review_note"] == "not good enough"


def test_schedule_post_sets_and_clears():
    post_id = _mk_post()
    posts_service.schedule_post(post_id, "2099-06-01")
    with connect() as conn:
        from claudeshorts.store import get_post
        assert get_post(conn, post_id)["scheduled_for"] == "2099-06-01"
    posts_service.schedule_post(post_id, None)
    with connect() as conn:
        from claudeshorts.store import get_post
        assert get_post(conn, post_id)["scheduled_for"] is None


def test_export_post_now_not_found_raises():
    with pytest.raises(ValueError, match="not found"):
        posts_service.export_post_now(999999)


def test_export_post_now_approves_and_exports(monkeypatch):
    post_id = _mk_post()
    called = {}
    monkeypatch.setattr(
        posts_service, "export_post",
        lambda post: called.setdefault("post_id", post["id"]) or [],
    )
    result = posts_service.export_post_now(post_id)
    assert result == {"post_id": post_id}
    assert called["post_id"] == post_id
    with connect() as conn:
        from claudeshorts.store import get_post
        assert get_post(conn, post_id)["status"] == "approved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_posts_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.services'`

- [ ] **Step 3: Implement `posts_service.py`**

```python
"""Post lifecycle actions shared by the CLI, dashboard, and (future) REST API
and Telegram bot. Each function is the single implementation of one
user-facing action — no route handler or CLI command should re-derive this
logic (goal.md: never duplicate business logic across interfaces).
"""

from __future__ import annotations

from typing import Any

from ..publish import export_post
from ..store import connect, get_post, set_schedule, set_status


def _require_post(conn, post_id: int) -> dict[str, Any]:
    post = get_post(conn, post_id)
    if not post:
        raise ValueError(f"post {post_id} not found")
    return post


def approve_post(post_id: int) -> dict[str, Any]:
    """Approve a post. Exports immediately unless it has a future schedule."""
    with connect() as conn:
        post = _require_post(conn, post_id)
        set_status(conn, post_id, "approved")
    scheduled_for = post.get("scheduled_for")
    if not scheduled_for:
        export_post(post)
        return {"post_id": post_id, "exported": True, "scheduled_for": None}
    return {"post_id": post_id, "exported": False, "scheduled_for": scheduled_for}


def reject_post(post_id: int, note: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        _require_post(conn, post_id)
        set_status(conn, post_id, "rejected", note=note)
    return {"post_id": post_id}


def schedule_post(post_id: int, scheduled_for: str | None) -> dict[str, Any]:
    with connect() as conn:
        _require_post(conn, post_id)
        set_schedule(conn, post_id, scheduled_for)
    return {"post_id": post_id, "scheduled_for": scheduled_for}


def export_post_now(post_id: int) -> dict[str, Any]:
    """Approve (if not already) and export right now, ignoring any schedule.

    Single implementation for what were two identical code paths
    (`/posts/{id}/export` and `/posts/{id}/publish-now`).
    """
    with connect() as conn:
        post = _require_post(conn, post_id)
        set_status(conn, post_id, "approved")
    export_post(post)
    return {"post_id": post_id}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_posts_service.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/services/__init__.py claudeshorts/services/posts_service.py tests/services/test_posts_service.py
git commit -m "feat: extract posts_service (approve/reject/schedule/export_now)"
```

---

### Task 2: `articles_service.py`

**Files:**
- Create: `claudeshorts/services/articles_service.py`
- Test: `tests/services/test_articles_service.py`

**Interfaces:**
- Consumes: `claudeshorts.store.{connect, insert_manual_item}`, `claudeshorts.store.pins.{pin_item, unpin_item}`, `claudeshorts.jobs.queue.enqueue`
- Produces: `add_manual_article(title, url=None, summary=None, action="pin") -> dict`, `pin_article(item_id) -> dict`, `unpin_article(item_id) -> dict`, `generate_from_item(item_id, *, display_title=None) -> dict` (returns `{"job_id": int}`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_articles_service.py
from __future__ import annotations

from claudeshorts.services import articles_service
from claudeshorts.store import connect
from claudeshorts.store.pins import is_pinned


def test_add_manual_article_pins_by_default():
    result = articles_service.add_manual_article(title="Hello World")
    assert result["created"] is True
    with connect() as conn:
        assert is_pinned(conn, result["item_id"]) is True
    assert "job_id" not in result


def test_add_manual_article_generate_action_enqueues_job():
    result = articles_service.add_manual_article(
        title="Hello Again", action="generate"
    )
    assert "job_id" in result
    with connect() as conn:
        assert is_pinned(conn, result["item_id"]) is False


def test_pin_and_unpin_article():
    result = articles_service.add_manual_article(title="Pin Me", action="pin")
    item_id = result["item_id"]
    articles_service.unpin_article(item_id)
    with connect() as conn:
        assert is_pinned(conn, item_id) is False
    articles_service.pin_article(item_id)
    with connect() as conn:
        assert is_pinned(conn, item_id) is True


def test_generate_from_item_enqueues_job():
    result = articles_service.add_manual_article(title="Gen Me", action="pin")
    out = articles_service.generate_from_item(result["item_id"])
    assert isinstance(out["job_id"], int)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_articles_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.services.articles_service'`

- [ ] **Step 3: Implement `articles_service.py`**

```python
"""Article intake actions (manual add, pin/unpin, generate-from-item) shared
by the dashboard and CLI.
"""

from __future__ import annotations

from typing import Any

from ..jobs import queue as job_queue
from ..store import connect, insert_manual_item
from ..store.pins import pin_item, unpin_item


def add_manual_article(
    title: str, url: str | None = None, summary: str | None = None,
    action: str = "pin",
) -> dict[str, Any]:
    """Insert an operator-supplied article, then either pin it or enqueue
    generation, matching the dashboard's "add article" form actions."""
    with connect() as conn:
        item_id, created = insert_manual_item(
            conn, title=title, url=url, summary=summary,
        )
    if action == "generate":
        out = generate_from_item(item_id, display_title=title)
        return {"item_id": item_id, "created": created, **out}
    with connect() as conn:
        pin_item(conn, item_id)
    return {"item_id": item_id, "created": created}


def pin_article(item_id: int) -> dict[str, Any]:
    with connect() as conn:
        pin_item(conn, item_id)
    return {"item_id": item_id}


def unpin_article(item_id: int) -> dict[str, Any]:
    with connect() as conn:
        unpin_item(conn, item_id)
    return {"item_id": item_id}


def generate_from_item(item_id: int, *, display_title: str | None = None) -> dict[str, Any]:
    name = (f"generate from “{display_title[:40]}”" if display_title
            else f"generate from item {item_id}")
    job_id = job_queue.enqueue("generate_from_item", {"item_id": item_id}, name=name)
    return {"job_id": job_id}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_articles_service.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/services/articles_service.py tests/services/test_articles_service.py
git commit -m "feat: extract articles_service (add/pin/unpin/generate-from-item)"
```

---

### Task 3: `pipeline_service.py`

**Files:**
- Create: `claudeshorts/services/pipeline_service.py`
- Test: `tests/services/test_pipeline_service.py`

**Interfaces:**
- Consumes: `claudeshorts.ingest.run_ingest`, `claudeshorts.generate.{run_generate, generate_for_item}`, `claudeshorts.render.render_post`, `claudeshorts.review.assemble_review`, `claudeshorts.orchestrate.run_pipeline`, `claudeshorts.store.{connect, get_post}`
- Produces: `run_ingest_service(since=None, limit=None) -> dict`, `run_generate_service(limit=None, on_progress=None) -> list[dict]`, `render_post_service(post_id) -> str`, `run_full_pipeline_service(limit=None, force=False, skip_render=False) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_pipeline_service.py
from __future__ import annotations

from unittest.mock import patch

import pytest

from claudeshorts.services import pipeline_service


def test_run_ingest_service_delegates():
    with patch("claudeshorts.services.pipeline_service.run_ingest") as mock_fn:
        mock_fn.return_value = {"fetched": 1}
        result = pipeline_service.run_ingest_service(since="2026-01-01", limit=5)
    mock_fn.assert_called_once_with(since="2026-01-01", limit=5)
    assert result == {"fetched": 1}


def test_run_generate_service_delegates():
    with patch("claudeshorts.services.pipeline_service.run_generate") as mock_fn:
        mock_fn.return_value = [{"post_id": 1}]
        result = pipeline_service.run_generate_service(limit=3)
    mock_fn.assert_called_once_with(limit=3, on_progress=None)
    assert result == [{"post_id": 1}]


def test_render_post_service_not_found_raises():
    with pytest.raises(ValueError, match="no post"):
        pipeline_service.render_post_service(999999)


def test_render_post_service_renders_and_assembles():
    with patch("claudeshorts.services.pipeline_service.get_post") as mock_get, \
         patch("claudeshorts.services.pipeline_service.render_post") as mock_render, \
         patch("claudeshorts.services.pipeline_service.assemble_review") as mock_assemble:
        mock_get.return_value = {"id": 7}
        mock_render.return_value = {"frames": 40}
        result = pipeline_service.render_post_service(7)
    mock_render.assert_called_once_with({"id": 7})
    mock_assemble.assert_called_once_with({"id": 7}, {"frames": 40})
    assert result == "rendered post 7: 40 frames"


def test_run_full_pipeline_service_delegates():
    with patch("claudeshorts.services.pipeline_service.run_pipeline") as mock_fn:
        mock_fn.return_value = {"date": "2026-07-10"}
        result = pipeline_service.run_full_pipeline_service(force=True)
    mock_fn.assert_called_once_with(limit=None, force=True, skip_render=False)
    assert result == {"date": "2026-07-10"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_pipeline_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.services.pipeline_service'`

- [ ] **Step 3: Implement `pipeline_service.py`**

```python
"""Wraps the ingest/generate/render/orchestrate pipeline entry points so the
CLI, dashboard, and job registry share one call site each — no domain logic
lives here, only the coordination (e.g. render + assemble the review bundle
as one step, since every caller wants both).
"""

from __future__ import annotations

from typing import Any, Callable

from ..generate import generate_for_item, run_generate
from ..ingest import run_ingest
from ..orchestrate import run_pipeline
from ..render import render_post
from ..review import assemble_review
from ..store import connect, get_post


def run_ingest_service(since: str | None = None, limit: int | None = None) -> dict[str, Any]:
    return run_ingest(since=since, limit=limit)


def run_generate_service(
    limit: int | None = None, on_progress: Callable[..., None] | None = None,
) -> list[dict[str, Any]]:
    return run_generate(limit=limit, on_progress=on_progress)


def generate_from_item_service(item_id: int) -> dict[str, Any]:
    return generate_for_item(item_id)


def render_post_service(post_id: int) -> str:
    with connect() as conn:
        post = get_post(conn, post_id)
    if not post:
        raise ValueError(f"no post {post_id}")
    result = render_post(post)
    assemble_review(post, result)
    return f"rendered post {post_id}: {result.get('frames')} frames"


def run_full_pipeline_service(
    limit: int | None = None, force: bool = False, skip_render: bool = False,
) -> dict[str, Any]:
    return run_pipeline(limit=limit, force=force, skip_render=skip_render)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_pipeline_service.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/services/pipeline_service.py tests/services/test_pipeline_service.py
git commit -m "feat: extract pipeline_service (ingest/generate/render/full_run)"
```

---

### Task 4: Simplify `jobs/registry.py` to a pure lookup table

**Files:**
- Modify: `claudeshorts/jobs/registry.py`
- Test: `tests/jobs/test_registry.py` (already exists from chunk 2 — must still pass)

**Interfaces:**
- Consumes: `services.pipeline_service.*`, `services.articles_service.generate_from_item` is NOT used here (job dispatch calls `pipeline_service.generate_from_item_service` directly, since the job's payload already has `item_id` — no need for the queue-enqueue wrapper `articles_service.generate_from_item` provides, which is for *creating* the job, not *running* it).
- Produces: same `JOB_HANDLERS` dict shape as chunk 2, same 5 keys.

- [ ] **Step 1: Run the existing chunk-2 registry test to confirm current behavior**

Run: `pytest tests/jobs/test_registry.py -v`
Expected: PASS (this is the baseline before refactoring)

- [ ] **Step 2: Replace `claudeshorts/jobs/registry.py`**

```python
"""Maps a job's `job_type` string to the service function that runs it.

No pipeline logic lives here — only the lookup. Business logic is in
`claudeshorts.services`, shared with the CLI and dashboard.
"""

from __future__ import annotations

from typing import Any, Callable

from ..services import pipeline_service

JOB_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "full_run": lambda payload: pipeline_service.run_full_pipeline_service(force=True),
    "ingest": lambda payload: pipeline_service.run_ingest_service(),
    "generate": lambda payload: pipeline_service.run_generate_service(),
    "generate_from_item": lambda payload: pipeline_service.generate_from_item_service(payload["item_id"]),
    "render_post": lambda payload: pipeline_service.render_post_service(payload["post_id"]),
}
```

- [ ] **Step 3: Run the existing registry + worker tests to verify no regression**

Run: `pytest tests/jobs/test_registry.py tests/jobs/test_worker.py -v`
Expected: PASS — chunk 2's tests patched `claudeshorts.jobs.registry.JOB_HANDLERS` and
`claudeshorts.generate.generate_for_item`/`claudeshorts.jobs.registry._render_post_by_id`
directly; the latter patch target no longer exists (`_render_post_by_id` is deleted). If
`test_registry.py`'s `test_render_post_unpacks_payload` fails because it patches a
now-nonexistent private function, update that one test to patch
`claudeshorts.services.pipeline_service.render_post_service` instead — this is
an intentional test update, not a regression, since the implementation detail
it was pinned to moved by design in this chunk.

- [ ] **Step 4: Commit**

```bash
git add claudeshorts/jobs/registry.py tests/jobs/test_registry.py
git commit -m "refactor: jobs/registry.py delegates to services, no inline pipeline logic"
```

---

### Task 5: Thin out `dashboard/app.py` route handlers

**Files:**
- Modify: `claudeshorts/dashboard/app.py`
- Test: existing dashboard tests (locate via `find tests -path '*dashboard*'`) plus any new ones needed for redirect-message coverage

**Interfaces:**
- Consumes: `services.posts_service.*`, `services.articles_service.*`

- [ ] **Step 1: Check for existing dashboard route tests**

Run: `find tests -iname "*dashboard*" -o -iname "*app*" | grep -v __pycache__`

If none exist beyond chunk 2's `tests/dashboard/test_jobs_stream.py`, add
route-level tests in Step 2 below rather than skipping verification.

- [ ] **Step 2: Write/extend tests for the affected routes**

```python
# tests/dashboard/test_posts_routes.py
from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard import create_app
from claudeshorts.store import connect, posts


def _mk_post():
    with connect() as conn:
        return posts.insert_post(
            conn, item_ids=[1], title="T", slides={}, captions={}
        )


def test_approve_redirects_with_message(monkeypatch):
    client = TestClient(create_app())
    post_id = _mk_post()
    from claudeshorts.services import posts_service
    monkeypatch.setattr(posts_service, "export_post", lambda post: [])
    resp = client.post(f"/posts/{post_id}/approve", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert "/review" in resp.headers["location"]


def test_export_and_publish_now_both_use_export_post_now(monkeypatch):
    client = TestClient(create_app())
    post_id = _mk_post()
    calls = []
    from claudeshorts.services import posts_service
    monkeypatch.setattr(
        posts_service, "export_post", lambda post: calls.append(post["id"]) or []
    )
    client.post(f"/posts/{post_id}/export", follow_redirects=False)
    client.post(f"/posts/{post_id}/publish-now", follow_redirects=False)
    assert calls == [post_id, post_id]
```

- [ ] **Step 3: Run tests to verify they fail against the current inline-logic handlers**

Run: `pytest tests/dashboard/test_posts_routes.py -v`
Expected: These may actually PASS already against current inline logic
(behavior is meant to be identical) — if so, that's fine; the point of
Step 2's tests is to pin current behavior before refactoring so a
regression in Step 4 is caught, not to force a red-green cycle where none
naturally exists for a pure refactor.

- [ ] **Step 4: Replace the 9 route handlers in `claudeshorts/dashboard/app.py`**

Replace each handler body (keep the route decorator and function
signature; only the body changes):

```python
@app.post("/posts/{post_id}/approve")
def approve(post_id: int):
    from ..services import posts_service
    try:
        result = posts_service.approve_post(post_id)
    except ValueError:
        return _redirect("/review", err="post not found")
    if result["exported"]:
        return _redirect("/review", msg=f"post {post_id} approved & exported")
    return _redirect(
        "/review", msg=f"post {post_id} approved; will publish {result['scheduled_for']}"
    )


@app.post("/posts/{post_id}/reject")
async def reject(post_id: int, request: Request):
    from ..services import posts_service
    note = (await _form(request)).get("note", "").strip() or None
    posts_service.reject_post(post_id, note=note)
    return _redirect("/review", msg=f"post {post_id} rejected")
```

```python
@app.post("/posts/{post_id}/export")
def post_export(post_id: int):
    from ..services import posts_service
    try:
        posts_service.export_post_now(post_id)
    except ValueError:
        return _redirect("/posts", err="post not found")
    except FileNotFoundError as exc:
        return _redirect("/posts", err=str(exc))
    return _redirect("/posts", msg=f"post {post_id} exported")


@app.post("/posts/{post_id}/schedule")
async def post_schedule(post_id: int, request: Request):
    from ..services import posts_service
    when = (await _form(request)).get("scheduled_for", "").strip() or None
    posts_service.schedule_post(post_id, when)
    where = request.headers.get("referer", "/posts")
    where = "/schedule" if "/schedule" in where else "/posts"
    return _redirect(where, msg=(f"post {post_id} scheduled for {when}" if when
                                 else f"post {post_id} schedule cleared"))


@app.post("/posts/{post_id}/publish-now")
def publish_now(post_id: int):
    from ..services import posts_service
    try:
        posts_service.export_post_now(post_id)
    except ValueError:
        return _redirect("/schedule", err="post not found")
    except FileNotFoundError as exc:
        return _redirect("/schedule", err=str(exc))
    return _redirect("/schedule", msg=f"post {post_id} published now")
```

```python
@app.post("/articles/add")
async def articles_add(request: Request):
    from ..services import articles_service
    f = await _form(request)
    title = (f.get("title") or "").strip()
    if not title:
        return _redirect("/articles", err="title is required")
    result = articles_service.add_manual_article(
        title=title,
        url=(f.get("url") or "").strip() or None,
        summary=(f.get("summary") or "").strip() or None,
        action=f.get("action", "pin"),
    )
    if "job_id" in result:
        return _redirect(f"/jobs/{result['job_id']}")
    verb = "added" if result["created"] else "already known; pinned"
    return _redirect("/articles", msg=f"article {verb} (#{result['item_id']})")


@app.post("/articles/{item_id}/generate")
def articles_generate(item_id: int):
    from ..services import articles_service
    result = articles_service.generate_from_item(item_id)
    return _redirect(f"/jobs/{result['job_id']}")


@app.post("/articles/{item_id}/pin")
def articles_pin(item_id: int):
    from ..services import articles_service
    articles_service.pin_article(item_id)
    return _redirect("/articles", msg=f"item {item_id} pinned for a future post")


@app.post("/articles/{item_id}/unpin")
def articles_unpin(item_id: int):
    from ..services import articles_service
    articles_service.unpin_article(item_id)
    return _redirect("/articles", msg=f"item {item_id} unpinned")
```

```python
@app.post("/posts/{post_id}/render")
def post_render(post_id: int):
    from ..jobs import queue as job_queue
    jid = job_queue.enqueue("render_post", {"post_id": post_id}, name=f"render post {post_id}")
    return _redirect(f"/jobs/{jid}")
```

(`post_render` already switched to `jobs.enqueue_job`/queue in chunk 2 —
double check against the Task 8 diff from the chunk-2 plan; if it already
calls `jobs.enqueue_job("render_post", ...)` there's nothing to change
here. Verify with `grep -n "def post_render" -A 5
claudeshorts/dashboard/app.py` before editing, and skip this snippet if
chunk 2's version is already in place.)

- [ ] **Step 5: Remove now-unused imports**

Run: `grep -n "from ..publish import export_post\|from ..store import.*set_status\|from ..store import.*set_schedule\|from ..store.pins import pin_item, unpin_item\|from ..generate import generate_for_item" claudeshorts/dashboard/app.py`

Remove any of these lazy imports that are no longer referenced inside
`dashboard/app.py` now that the logic moved to `services/`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/dashboard/ -v`
Expected: PASS (all)

- [ ] **Step 7: Manual verification**

Run: `./start-dashboard.sh`, click through: approve a rendered post
(confirm export happens for unscheduled posts), reject a post with a note,
set and clear a schedule, add a manual article via both "pin" and
"generate" actions, export and publish-now on two different posts (confirm
both work identically).

- [ ] **Step 8: Commit**

```bash
git add claudeshorts/dashboard/app.py tests/dashboard/test_posts_routes.py
git commit -m "refactor: dashboard route handlers delegate to services, no inline business logic"
```

---

### Task 6: Point CLI commands at the service layer

**Files:**
- Modify: `claudeshorts/cli.py`
- Test: `tests/test_cli.py` (create if none exists — check first)

**Interfaces:**
- Consumes: `services.pipeline_service.*`

- [ ] **Step 1: Check for an existing CLI test file**

Run: `find tests -iname "*cli*"`

- [ ] **Step 2: Write/extend a CLI smoke test**

```python
# tests/test_cli.py
from __future__ import annotations

from typer.testing import CliRunner
from unittest.mock import patch

from claudeshorts.cli import app

runner = CliRunner()


def test_ingest_cmd_calls_pipeline_service():
    with patch("claudeshorts.cli.pipeline_service.run_ingest_service") as mock_fn:
        mock_fn.return_value = {
            "fetched": 1, "stored": 1, "duplicates": 0, "skipped_old": 0,
            "total_items": 1, "by_source": {},
        }
        result = runner.invoke(app, ["ingest"])
    assert result.exit_code == 0
    mock_fn.assert_called_once()


def test_run_cmd_calls_pipeline_service():
    with patch("claudeshorts.cli.pipeline_service.run_full_pipeline_service") as mock_fn:
        mock_fn.return_value = {"skipped": True, "reason": "already ran", "date": "2026-07-10"}
        result = runner.invoke(app, ["run"])
    assert result.exit_code == 0
    mock_fn.assert_called_once()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — `AttributeError: module 'claudeshorts.cli' has no attribute 'pipeline_service'` (not yet imported)

- [ ] **Step 4: Update `claudeshorts/cli.py`'s `ingest`, `generate`, `render`, `run` commands**

Add the import near the top-level imports:
```python
from . import services
from .services import pipeline_service
```

In `ingest_cmd`, replace `from .ingest import run_ingest` + `run_ingest(since=since, limit=limit)` with:
```python
stats = pipeline_service.run_ingest_service(since=since, limit=limit)
```

In `generate_cmd`, replace `from .generate import run_generate` + `run_generate(limit=limit, on_progress=cb)` with:
```python
results = pipeline_service.run_generate_service(limit=limit, on_progress=cb)
```

In `render_cmd`, replace the body from `from .render import render_post` through
the `assemble_review(post, result)` call with a single call, adapting the
`typer.echo` lines to use its return value:
```python
@app.command("render")
def render_cmd(post_id: int = typer.Argument(..., help="posts.id to render.")) -> None:
    """Render a post's slides to an MP4 via the Node renderer. [Phase 3]"""
    init_db()
    try:
        summary = pipeline_service.render_post_service(post_id)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    typer.echo(summary)
```

(Note: this simplifies the CLI's render output to the same one-line
summary the dashboard/job log shows, rather than the CLI's previous
multi-line frames/duration/audio-mode/review-folder breakdown — flag this
as a minor UX regression for the render CLI command specifically and
confirm with the user in Step 6 below whether the richer CLI output should
be preserved by having `render_post_service` return a dict instead of a
string. Default to preserving richer output: change
`pipeline_service.render_post_service`'s return type to `dict[str, Any]`
carrying `{"frames", "duration_ms", "audio_mode", "review_dir"}` instead of
a formatted string, and update `render_cmd`, `jobs/registry.py`'s lambda,
and `test_pipeline_service.py`'s assertions accordingly before treating
this task as done.)

In `run_cmd`, replace `from .orchestrate import run_pipeline` +
`run_pipeline(limit=limit, force=force, skip_render=skip_render)` with:
```python
summary = pipeline_service.run_full_pipeline_service(limit=limit, force=force, skip_render=skip_render)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 6: Resolve the render-output-format note from Step 4**

Before committing, decide (per the note above) whether
`render_post_service` returns a string or a dict, and make it consistent
across `pipeline_service.py`, `jobs/registry.py`, `cli.py`, and their
tests. Default: dict, since it preserves more information for every
caller and the CLI's richer historical output.

- [ ] **Step 7: Manual verification**

Run: `python -m claudeshorts.cli ingest`, `python -m claudeshorts.cli
generate`, `python -m claudeshorts.cli render <a-post-id>`,
`python -m claudeshorts.cli run` — confirm output matches pre-refactor
formatting (modulo the deliberate render-output resolution from Step 6).

- [ ] **Step 8: Commit**

```bash
git add claudeshorts/cli.py claudeshorts/services/pipeline_service.py claudeshorts/jobs/registry.py tests/test_cli.py tests/services/test_pipeline_service.py
git commit -m "refactor: CLI commands call services.pipeline_service instead of pipeline internals"
```

---

### Task 7: Update checkpoint and task tracking

**Files:**
- Modify: `CHECKPOINT_LAST.md`, `TASK_QUEUE.md`

- [ ] **Step 1: Record completion**

Update `TASK_QUEUE.md` to move chunk 3 to Done. Update `CHECKPOINT_LAST.md`
with next action: chunk 4 (REST API over services).

- [ ] **Step 2: Commit**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 3 complete — service layer extracted, CLI/dashboard/registry all thin callers"
```

---

## Self-Review Notes

**Spec coverage:** `posts_service` (approve/reject/schedule/export_now,
unifying the export/publish-now duplicate) → Task 1. `articles_service`
(add/pin/unpin/generate-from-item) → Task 2. `pipeline_service`
(ingest/generate/render/full_run) → Task 3. `jobs/registry.py` reduced to
a pure lookup → Task 4. Dashboard route handlers thinned → Task 5. CLI
commands thinned → Task 6. Settings handlers correctly left untouched per
spec's explicit out-of-scope note.

**Placeholder scan:** Task 6 Step 4 flags a real design ambiguity
discovered during planning (string vs. dict return for
`render_post_service`) rather than silently picking one and hiding the
tradeoff — Step 6 forces it to be resolved consistently before the task is
considered done, which is a deliberate decision point, not a placeholder.

**Type consistency:** `posts_service.approve_post`'s return dict shape
(`post_id`, `exported`, `scheduled_for`) matches its test assertions and
its dashboard caller in Task 5. `articles_service.add_manual_article`'s
conditional `job_id` key (present only for `action="generate"`) is checked
consistently via `"job_id" in result` in both its test and the
`/articles/add` handler. `jobs/registry.py`'s lambda signatures
(`payload -> Any`) are unchanged from chunk 2, so `worker.py` needs no
changes in this chunk.
