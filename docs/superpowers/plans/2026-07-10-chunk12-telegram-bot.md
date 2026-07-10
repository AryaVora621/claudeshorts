# Chunk 12: Telegram Bot Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot that satisfies every capability goal.md requires (generate, view queue, approve/reject, retry, view profiles, monitor workers, notifications, logs) purely by calling chunk 4's REST API — no duplicated business logic — restricted to one admin chat.

**Architecture:** Two small REST API additions (`GET /profiles`, `POST /jobs/{id}/retry`); a new `claudeshorts/telegram_bot/` package with an `ApiClient` HTTP wrapper, command handlers, and a `notify.py` push helper wired into the existing job worker and scheduler.

**Tech Stack:** Python 3.11+, new dependency `python-telegram-bot>=21`, existing `httpx`, existing FastAPI app (chunk 4).

## Global Constraints

- No comments explaining *what*, only non-obvious *why*.
- Every bot command handler calls exactly one `ApiClient` method — no business logic in `bot.py` beyond text formatting.
- The bot only responds to `TELEGRAM_CHAT_ID`; every other chat gets a fixed rejection and no API call.
- Full spec: `docs/superpowers/specs/2026-07-10-chunk12-telegram-bot-design.md`.

---

## File Structure

- Modify: `claudeshorts/api/profiles.py` (new file), `claudeshorts/api/jobs.py`, `claudeshorts/api/__init__.py`, `pyproject.toml`
- Create: `claudeshorts/telegram_bot/__init__.py`, `client.py`, `bot.py`, `notify.py`, `__main__.py`
- Modify: `claudeshorts/jobs/worker.py` (chunk 2), `claudeshorts/scheduling/scheduler.py` (chunk 5)
- Test: `tests/api/test_profiles_api.py`, `tests/api/test_jobs_retry.py`, `tests/telegram_bot/test_client.py`, `tests/telegram_bot/test_bot.py`

---

### Task 1: `GET /api/v1/profiles` + `POST /api/v1/jobs/{id}/retry`

**Files:**
- Create: `claudeshorts/api/profiles.py`
- Modify: `claudeshorts/api/jobs.py`, `claudeshorts/api/__init__.py`
- Test: `tests/api/test_profiles_api.py`, `tests/api/test_jobs_retry.py`

**Interfaces:**
- Consumes: `browser.profiles.list_profiles()` (chunk 11), `jobs.queue.enqueue`/`get_job` (chunk 2).
- Produces: `GET /api/v1/profiles`, `POST /api/v1/jobs/{id}/retry`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_profiles_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard.app import create_app
import claudeshorts.browser.profiles as profiles_mod


def test_get_profiles_returns_list(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    (tmp_path / "acme-youtube.yaml").write_text(
        "slug: acme-youtube\nplatform: youtube\nlogin_health: ok\n"
    )
    client = TestClient(create_app())
    resp = client.get("/api/v1/profiles")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [{"slug": "acme-youtube", "platform": "youtube", "login_health": "ok"}]


def test_get_profiles_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", tmp_path)
    client = TestClient(create_app())
    resp = client.get("/api/v1/profiles")
    assert resp.status_code == 200
    assert resp.json() == []
```

```python
# tests/api/test_jobs_retry.py
from __future__ import annotations

from fastapi.testclient import TestClient

from claudeshorts.dashboard.app import create_app
from claudeshorts.jobs import queue


def test_retry_failed_job_reenqueues(db, monkeypatch):
    # Confirm exact enqueue/fail signatures against chunk 2's actual
    # jobs/queue.py before writing this test for real — illustrative shape:
    job_id = queue.enqueue(db, job_type="generate", payload={"count": 1})
    job = queue.claim_next(db, worker_id="w1")
    queue.fail(db, job["id"], error="boom")

    client = TestClient(create_app())
    resp = client.post(f"/api/v1/jobs/{job['id']}/retry")
    assert resp.status_code == 200
    new_job_id = resp.json()["job_id"]
    assert new_job_id != job["id"]


def test_retry_non_failed_job_returns_409():
    client = TestClient(create_app())
    resp = client.post("/api/v1/jobs/999999/retry")
    assert resp.status_code in (404, 409)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_profiles_api.py tests/api/test_jobs_retry.py -v`
Expected: FAIL — `404 Not Found` (routes don't exist yet)

- [ ] **Step 3: Implement `api/profiles.py`**

```python
"""Read-only per chunk 12's confirmed scope — no endpoint to create or
log into a profile from the API; that requires a visible browser on the
host (chunk 11's interactive_login.py)."""

from __future__ import annotations

from fastapi import APIRouter

from ..browser import profiles

router = APIRouter()


@router.get("/profiles")
def list_profiles() -> list[dict]:
    return [
        {"slug": p["slug"], "platform": p["platform"], "login_health": p["login_health"]}
        for p in profiles.list_profiles()
    ]
```

- [ ] **Step 4: Implement the retry route in `api/jobs.py`**

Locate the existing router (`grep -n "router = APIRouter\|@router.post" claudeshorts/api/jobs.py`)
and add:

```python
@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int):
    with connect() as conn:
        job = jobs_queue.get_job(conn, job_id)
        if job is None:
            raise HTTPException(404, f"job {job_id} not found")
        if job["status"] != "failed":
            raise HTTPException(409, f"job {job_id} is not failed (status={job['status']})")
        new_id = jobs_queue.enqueue(conn, job_type=job["job_type"], payload=job["payload"])
        conn.commit()
    return {"job_id": new_id}
```

(Match import names — `jobs_queue`, `connect`, `HTTPException` — to
whatever `api/jobs.py` already imports; add only what's missing.)

- [ ] **Step 5: Register the new router**

In `claudeshorts/api/__init__.py`, add `from . import profiles` and
`router.include_router(profiles.router)` alongside the existing
posts/articles/pipeline/jobs router registrations.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/api/test_profiles_api.py tests/api/test_jobs_retry.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Run the full API test suite to check for regressions**

Run: `pytest tests/api/ -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add claudeshorts/api/profiles.py claudeshorts/api/jobs.py claudeshorts/api/__init__.py tests/api/test_profiles_api.py tests/api/test_jobs_retry.py
git commit -m "feat: add GET /profiles and POST /jobs/{id}/retry REST endpoints"
```

---

### Task 2: `telegram_bot/client.py` — `ApiClient`

**Files:**
- Create: `claudeshorts/telegram_bot/__init__.py` (empty)
- Create: `claudeshorts/telegram_bot/client.py`
- Test: `tests/telegram_bot/test_client.py`

**Interfaces:**
- Produces: `ApiClient(base_url).generate(count)`, `.list_posts(status=None)`, `.approve(post_id)`, `.reject(post_id, note=None)`, `.list_jobs(status=None)`, `.get_job(job_id)`, `.retry_job(job_id)`, `.list_profiles()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/telegram_bot/test_client.py
from __future__ import annotations

import httpx

from claudeshorts.telegram_bot.client import ApiClient


def _mock_client(handler):
    return ApiClient(base_url="http://testserver", transport=httpx.MockTransport(handler))


def test_generate_posts_to_pipeline_generate():
    seen = {}
    def handler(request):
        seen["method"], seen["path"], seen["json"] = request.method, request.url.path, httpx.Request(request.method, request.url, content=request.content).content
        return httpx.Response(202, json={"job_id": 7})
    client = _mock_client(handler)
    result = client.generate(3)
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/pipeline/generate"
    assert result == {"job_id": 7}


def test_list_posts_with_status_filter():
    def handler(request):
        assert request.url.path == "/api/v1/posts"
        assert dict(request.url.params) == {"status": "rendered"}
        return httpx.Response(200, json=[{"id": 1, "title": "T"}])
    client = _mock_client(handler)
    assert client.list_posts(status="rendered") == [{"id": 1, "title": "T"}]


def test_approve_calls_correct_endpoint():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/posts/5/approve"
        return httpx.Response(200, json={"post_id": 5, "exported": True, "scheduled_for": None})
    client = _mock_client(handler)
    result = client.approve(5)
    assert result["exported"] is True


def test_retry_job_calls_correct_endpoint():
    def handler(request):
        assert request.url.path == "/api/v1/jobs/9/retry"
        return httpx.Response(200, json={"job_id": 10})
    client = _mock_client(handler)
    assert client.retry_job(9) == {"job_id": 10}


def test_list_profiles():
    def handler(request):
        assert request.url.path == "/api/v1/profiles"
        return httpx.Response(200, json=[{"slug": "a", "platform": "youtube", "login_health": "ok"}])
    client = _mock_client(handler)
    assert client.list_profiles()[0]["slug"] == "a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/telegram_bot/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.telegram_bot'`

- [ ] **Step 3: Implement `client.py`**

```python
"""Thin 1:1 wrapper over /api/v1/* — every method is exactly one HTTP
call, no branching logic, so bot.py's handlers stay pure formatting."""

from __future__ import annotations

import httpx


class ApiClient:
    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(base_url=base_url, transport=transport, timeout=30)

    def generate(self, count: int) -> dict:
        return self._http.post("/api/v1/pipeline/generate", json={"count": count}).json()

    def list_posts(self, status: str | None = None) -> list[dict]:
        params = {"status": status} if status else {}
        return self._http.get("/api/v1/posts", params=params).json()

    def approve(self, post_id: int) -> dict:
        return self._http.post(f"/api/v1/posts/{post_id}/approve").json()

    def reject(self, post_id: int, note: str | None = None) -> dict:
        return self._http.post(f"/api/v1/posts/{post_id}/reject", json={"note": note}).json()

    def list_jobs(self, status: str | None = None) -> list[dict]:
        params = {"status": status} if status else {}
        return self._http.get("/api/v1/jobs", params=params).json()

    def get_job(self, job_id: int) -> dict:
        return self._http.get(f"/api/v1/jobs/{job_id}").json()

    def retry_job(self, job_id: int) -> dict:
        return self._http.post(f"/api/v1/jobs/{job_id}/retry").json()

    def list_profiles(self) -> list[dict]:
        return self._http.get("/api/v1/profiles").json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/telegram_bot/test_client.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/telegram_bot/__init__.py claudeshorts/telegram_bot/client.py tests/telegram_bot/test_client.py
git commit -m "feat: add ApiClient — thin HTTP wrapper over the REST API for the Telegram bot"
```

---

### Task 3: `bot.py` — command handlers + chat-id allowlist

**Files:**
- Create: `claudeshorts/telegram_bot/bot.py`
- Modify: `pyproject.toml`
- Test: `tests/telegram_bot/test_bot.py`

**Interfaces:**
- Consumes: `ApiClient` (Task 2).
- Produces: `build_application(token: str, chat_id: int, client: ApiClient) -> telegram.ext.Application`, `format_queue(posts: list[dict]) -> str`, `format_job(job: dict) -> str` (pure formatting functions, independently testable without a real Telegram connection).

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`'s `dependencies`, add:
```toml
    "python-telegram-bot>=21.0",
```
Run: `pip install -e .`

- [ ] **Step 2: Write the failing tests**

```python
# tests/telegram_bot/test_bot.py
from __future__ import annotations

from unittest.mock import MagicMock

from claudeshorts.telegram_bot.bot import format_queue, format_job, is_authorized


def test_format_queue_lists_titles_and_ids():
    posts = [{"id": 1, "title": "GPT-5.5 ships"}, {"id": 2, "title": "Nvidia earnings"}]
    text = format_queue(posts)
    assert "1" in text and "GPT-5.5 ships" in text
    assert "2" in text and "Nvidia earnings" in text


def test_format_queue_empty():
    assert "no posts" in format_queue([]).lower()


def test_format_job_includes_status_and_id():
    job = {"id": 9, "status": "failed", "job_type": "generate", "attempts": 3, "error": "boom"}
    text = format_job(job)
    assert "9" in text and "failed" in text and "boom" in text


def test_is_authorized_matches_configured_chat_id():
    assert is_authorized(chat_id=555, allowed_chat_id=555) is True
    assert is_authorized(chat_id=1, allowed_chat_id=555) is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/telegram_bot/test_bot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claudeshorts.telegram_bot.bot'`

- [ ] **Step 4: Implement `bot.py`**

```python
"""Every handler: parse args -> one ApiClient call -> format text. No
business logic here — that's the whole point of calling the REST API
instead of claudeshorts.services directly."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .client import ApiClient


def is_authorized(chat_id: int, allowed_chat_id: int) -> bool:
    return chat_id == allowed_chat_id


def format_queue(posts: list[dict]) -> str:
    if not posts:
        return "No posts awaiting review."
    return "\n".join(f"#{p['id']}: {p['title']}" for p in posts)


def format_job(job: dict) -> str:
    text = f"Job #{job['id']} ({job['job_type']}): {job['status']}, attempts={job['attempts']}"
    if job.get("error"):
        text += f"\nerror: {job['error']}"
    return text


def build_application(token: str, chat_id: int, client: ApiClient) -> Application:
    app = Application.builder().token(token).build()

    async def guard(update: Update) -> bool:
        if not is_authorized(update.effective_chat.id, chat_id):
            await update.message.reply_text("Not authorized.")
            return False
        return True

    async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        posts = client.list_posts(status="rendered")
        await update.message.reply_text(format_queue(posts))

    async def generate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        count = int(context.args[0]) if context.args else 1
        result = client.generate(count)
        await update.message.reply_text(f"Enqueued job #{result['job_id']}")

    async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        post_id = int(context.args[0])
        result = client.approve(post_id)
        await update.message.reply_text(f"Approved post #{post_id}: {result}")

    async def reject_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        post_id = int(context.args[0])
        note = " ".join(context.args[1:]) if len(context.args) > 1 else None
        client.reject(post_id, note=note)
        await update.message.reply_text(f"Rejected post #{post_id}")

    async def retry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        job_id = int(context.args[0])
        result = client.retry_job(job_id)
        await update.message.reply_text(f"Retried as job #{result['job_id']}")

    async def profiles_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        profiles = client.list_profiles()
        if not profiles:
            await update.message.reply_text("No profiles configured yet.")
            return
        text = "\n".join(f"{p['slug']} ({p['platform']}): {p['login_health']}" for p in profiles)
        await update.message.reply_text(text)

    async def workers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        jobs = client.list_jobs(status="running")
        text = "\n".join(format_job(j) for j in jobs) or "No running jobs."
        await update.message.reply_text(text)

    async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        job = client.get_job(int(context.args[0]))
        await update.message.reply_text(f"{format_job(job)}\n\n{job.get('log', '')}"[:4000])

    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CommandHandler("generate", generate_cmd))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("reject", reject_cmd))
    app.add_handler(CommandHandler("retry", retry_cmd))
    app.add_handler(CommandHandler("profiles", profiles_cmd))
    app.add_handler(CommandHandler("workers", workers_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    return app
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/telegram_bot/test_bot.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add claudeshorts/telegram_bot/bot.py pyproject.toml tests/telegram_bot/test_bot.py
git commit -m "feat: add Telegram command handlers with single-admin-chat authorization"
```

---

### Task 4: `notify.py` + `__main__.py` + worker/scheduler hooks

**Files:**
- Create: `claudeshorts/telegram_bot/notify.py`, `claudeshorts/telegram_bot/__main__.py`
- Modify: `claudeshorts/jobs/worker.py`, `claudeshorts/scheduling/scheduler.py`

**Interfaces:**
- Produces: `send_notification(text: str) -> None`.

- [ ] **Step 1: Implement `notify.py`**

```python
"""Push notifications — separate from bot.py's pull-based commands.
Fire-and-forget: a notification failure must never break the job/
scheduler pipeline that triggered it, so exceptions are logged, not
raised."""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)


def send_notification(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000]},
            timeout=10,
        )
    except Exception as exc:
        log.warning("Telegram notification failed: %s", exc)
```

- [ ] **Step 2: Implement `__main__.py`**

```python
"""python -m claudeshorts.telegram_bot — starts the long-polling loop."""

import os

from .bot import build_application
from .client import ApiClient


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = int(os.environ["TELEGRAM_CHAT_ID"])
    base_url = os.environ.get("CLAUDESHORTS_API_BASE_URL", "http://127.0.0.1:8000")
    client = ApiClient(base_url=base_url)
    app = build_application(token, chat_id, client)
    app.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Wire notification hooks**

In `claudeshorts/jobs/worker.py`'s job-completion path (chunk 2's
`dispatch_one`, where it logs `"job %s (%s) completed/failed"` per chunk
6's plan), add after a failure is recorded:

```python
from ..telegram_bot.notify import send_notification
...
send_notification(f"Job #{job['id']} ({job['job_type']}) failed: {error}")
```

In `claudeshorts/scheduling/scheduler.py`, after the `weekly_report` job
type completes (chunk 5's scheduler polling loop), add:

```python
send_notification(f"Weekly report ready — job #{job['id']}. Use /logs {job['id']} to view.")
```

- [ ] **Step 4: Run the full test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: PASS (notify.py's real network call is never exercised in
tests since `TELEGRAM_BOT_TOKEN` is unset in the test environment — the
function returns early)

- [ ] **Step 5: Commit**

```bash
git add claudeshorts/telegram_bot/notify.py claudeshorts/telegram_bot/__main__.py claudeshorts/jobs/worker.py claudeshorts/scheduling/scheduler.py
git commit -m "feat: add Telegram push notifications on job failure and weekly report completion"
```

---

### Task 5: Update checkpoint and task tracking

**Files:**
- Modify: `CHECKPOINT_LAST.md`, `TASK_QUEUE.md`

- [ ] **Step 1: Record completion, flag the remaining human-required step**

Update `TASK_QUEUE.md` to move chunk 12 to Done. Update
`CHECKPOINT_LAST.md` noting: the bot's full command surface, notification
hooks, and REST API additions are implemented and tested against a mocked
Telegram/API layer; creating a real bot via BotFather and setting
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` to run it live remains the
explicit human-required final task. Next action: chunk 13
(Higgsfield/Veo research).

- [ ] **Step 2: Commit**

```bash
git add TASK_QUEUE.md CHECKPOINT_LAST.md
git commit -m "docs: chunk 12 complete — Telegram bot implemented and tested, real bot token still pending"
```

---

## Self-Review Notes

**Spec coverage:** Every capability in goal.md's required list maps to
exactly one command in Task 3's table, matching the spec's command
surface. `GET /profiles`/`POST /jobs/{id}/retry` (Task 1) fill the two
real gaps the spec identified. `ApiClient` (Task 2) is a pure 1:1 HTTP
wrapper per the spec's "no branching logic" requirement. Single-admin-chat
authorization (Task 3's `is_authorized`/`guard`) matches the spec's
security-boundary requirement. `notify.py` (Task 4) matches the spec's
push-vs-pull distinction and its explicit "fire-and-forget, never breaks
the pipeline" design.

**Placeholder scan:** Task 1 Step 1's test file includes a comment
flagging that the exact `queue.enqueue`/`queue.fail` signatures should be
confirmed against chunk 2's real `jobs/queue.py` before the test is
finalized — this is an explicit confirmation instruction, not a vague
placeholder, since this plan cannot see chunk 2's plan's exact final
signatures if chunk 2 hasn't been executed yet. No other placeholder
patterns found.

**Type consistency:** `ApiClient`'s method names (Task 2) match `bot.py`'s
handler calls one-to-one (Task 3) — `generate`, `list_posts`, `approve`,
`reject`, `retry_job`, `list_profiles`, `list_jobs`, `get_job`. `format_job`
/`format_queue`'s expected dict shapes (`id`, `title`, `status`,
`job_type`, `attempts`, `error`, `log`) match the REST API's existing
`JobResponse`/posts schema from chunk 4's spec. `send_notification`'s
signature is identical at both call sites (Task 4 Step 3).
