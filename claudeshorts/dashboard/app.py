"""The local operator dashboard (FastAPI, server-rendered).

A single-process console over the local pipeline state (SQLite + the review/
publish folders). Sections: Overview, Review queue, Articles (browse + manually
add/generate/pin), Posts, Schedule (future-posts queue), Threads, Runs history,
and Settings (connect your Anthropic account + tune the pipeline).

Bind to localhost — this is an operator tool, not a public service. Slow actions
(ingest/generate/render/full run) execute as background jobs whose logs stream
live to the browser (see ``jobs`` + the ``/jobs`` routes).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import api, config
from ..store import connect
from . import auth, jobs, settings_io

_HERE = Path(__file__).resolve().parent
_templates = Jinja2Templates(directory=str(_HERE / "templates"))


def _format_timestamp(value: object, length: int | None) -> str:
    """Render a DB timestamp for display.

    Postgres (psycopg3) returns TIMESTAMPTZ columns as ``datetime.datetime``;
    the old SQLite store returned them as ISO strings. Templates historically
    string-sliced the ISO string (e.g. ``[:16]``) to trim to "YYYY-MM-DD HH:MM" —
    accept either shape here so callers don't care which store produced the row.
    """
    if value is None:
        return ""
    text = value.isoformat(sep=" ") if isinstance(value, datetime) else str(value)
    return text[:length] if length is not None else text


# Jinja filters used by templates in place of raw string-slicing on timestamp
# columns, which breaks once a column comes back as `datetime` instead of `str`.
_templates.env.filters["tshort"] = lambda v: _format_timestamp(v, 16)  # "YYYY-MM-DD HH:MM"
_templates.env.filters["tsfull"] = lambda v: _format_timestamp(v, 19)  # "YYYY-MM-DD HH:MM:SS"
_templates.env.filters["tsdate"] = lambda v: _format_timestamp(v, 10)  # "YYYY-MM-DD"

# Media names the dashboard will serve for a post: the video, its poster, and
# the carousel stills (``slides/slide_NN.png``). The strict slide pattern keeps
# the path-joined media lookup from being abused for traversal.
_SLIDE_RE = re.compile(r"^slides/slide_\d{2,}\.png$")


# --- small helpers ---------------------------------------------------------
async def _form(request: Request) -> dict[str, str]:
    """Parse a urlencoded form body (avoids a python-multipart dependency)."""
    body = (await request.body()).decode("utf-8")
    return {k: v[0] for k, v in parse_qs(body).items()}


def _redirect(path: str, *, msg: str | None = None, err: str | None = None):
    params = {k: v for k, v in (("msg", msg), ("err", err)) if v}
    if params:
        path = f"{path}?{urlencode(params)}"
    return RedirectResponse(path, status_code=303)


def _media_path(post_id: int, name: str) -> Path | None:
    """Locate a post's rendered media: review bundle first, then the render dir."""
    from ..review.queue import review_dir_for

    path = review_dir_for(post_id) / name
    if path.exists():
        return path
    matches = sorted(config.REVIEW_DIR.glob(f"*/post_{post_id}/{name}"))
    if matches:
        return matches[-1]
    rendered = config.RENDERS_DIR / f"post_{post_id}" / name
    return rendered if rendered.exists() else None


def create_app() -> FastAPI:
    app = FastAPI(title="claudeshorts dashboard")
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")
    app.include_router(api.router)

    @app.on_event("startup")
    def _start_job_worker() -> None:
        import threading

        from ..jobs.worker import run_forever
        from ..scheduling.scheduler import run_forever as run_scheduler_forever
        from ..scheduling.scheduler import seed_default_schedules

        threading.Thread(
            target=run_forever, args=("dashboard-worker",), daemon=True,
        ).start()

        seed_default_schedules()
        threading.Thread(target=run_scheduler_forever, daemon=True).start()

    def page(request: Request, name: str, **ctx):
        ctx.setdefault("active", "")
        ctx["msg"] = request.query_params.get("msg")
        ctx["err"] = request.query_params.get("err")
        ctx["channel"] = config.settings().get("channel", {}).get("name", "claudeshorts")
        return _templates.TemplateResponse(request, name, ctx)

    # --- Overview ----------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        from ..store import count_items, status_counts, scheduled_posts
        from ..store.pins import pinned_items
        from ..store.runs import recent_runs

        with connect() as conn:
            counts = status_counts(conn)
            n_items = count_items(conn)
            n_pinned = len(pinned_items(conn))
            n_scheduled = len(scheduled_posts(conn))
            runs = recent_runs(conn, 1)
        return page(
            request, "overview.html", active="overview",
            counts=counts, n_items=n_items, n_pinned=n_pinned,
            n_scheduled=n_scheduled, last_run=runs[0] if runs else None,
            recent_jobs=jobs.recent_jobs(8), backend=auth.current_backend(),
        )

    # --- Pipeline actions (background jobs) --------------------------------
    @app.post("/actions/{name}")
    def action(name: str):
        if name == "run":
            jid = jobs.enqueue_job("full_run", {}, "daily run")
        elif name == "ingest":
            jid = jobs.enqueue_job("ingest", {}, "ingest")
        elif name == "generate":
            jid = jobs.enqueue_job("generate", {}, "generate")
        else:
            return _redirect("/", err=f"unknown action {name}")
        return _redirect(f"/jobs/{jid}")

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs_list(request: Request):
        return page(request, "jobs.html", active="jobs", jobs=jobs.recent_jobs(50))

    @app.get("/jobs.json")
    def jobs_json(request: Request):
        try:
            limit = max(1, min(200, int(request.query_params.get("limit", 50))))
        except ValueError:
            limit = 50
        return JSONResponse({"jobs": [j.to_dict() for j in jobs.recent_jobs(limit)]})

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_detail(request: Request, job_id: int):
        job = jobs.get_job(job_id)
        if not job:
            return _redirect("/", err="no such job")
        return page(request, "job.html", active="jobs", job=job)

    @app.get("/jobs/{job_id}/stream")
    def job_stream(job_id: int):
        return StreamingResponse(
            jobs.stream(job_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # --- Review queue ------------------------------------------------------
    @app.get("/review", response_class=HTMLResponse)
    def review(request: Request):
        from ..review.queue import carousel_slides, pending_reviews
        from ..review.captions import PLATFORM_CAPTION

        posts = pending_reviews()
        caps = {p["id"]: {pl: fn(p.get("captions") or {})
                          for pl, fn in PLATFORM_CAPTION.items()} for p in posts}
        decks = {p["id"]: carousel_slides(p["id"]) for p in posts}
        return page(request, "review.html", active="review",
                    posts=posts, caps=caps, decks=decks)

    @app.get("/media/{post_id}/{name:path}")
    def media(post_id: int, name: str):
        if name not in ("video.mp4", "thumb.png") and not _SLIDE_RE.match(name):
            return HTMLResponse("not found", status_code=404)
        path = _media_path(post_id, name)
        if not path:
            return HTMLResponse("not found", status_code=404)
        return FileResponse(path)

    @app.post("/posts/{post_id}/approve")
    def approve(post_id: int):
        from ..services import posts_service

        try:
            result = posts_service.approve_post(post_id)
        except ValueError:
            return _redirect("/review", err="post not found")
        except FileNotFoundError as exc:
            return _redirect("/review", err=str(exc))
        if result["exported"]:
            return _redirect("/review", msg=f"post {post_id} approved & exported")
        return _redirect(
            "/review",
            msg=f"post {post_id} approved; will publish {result['scheduled_for']}",
        )

    @app.post("/posts/{post_id}/reject")
    async def reject(post_id: int, request: Request):
        from ..services import posts_service

        note = (await _form(request)).get("note", "").strip() or None
        posts_service.reject_post(post_id, note=note)
        return _redirect("/review", msg=f"post {post_id} rejected")

    # --- Articles ----------------------------------------------------------
    @app.get("/articles", response_class=HTMLResponse)
    def articles(request: Request):
        from ..store import latest_items
        from ..store.pins import pinned_item_ids, pinned_items

        with connect() as conn:
            items = latest_items(conn, 120)
            pinned = pinned_items(conn)
            pinned_ids = set(pinned_item_ids(conn))
        return page(request, "articles.html", active="articles",
                    items=items, pinned=pinned, pinned_ids=pinned_ids)

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

    # --- Posts -------------------------------------------------------------
    @app.get("/posts", response_class=HTMLResponse)
    def posts(request: Request):
        from ..review.queue import carousel_slides
        from ..store import all_posts

        with connect() as conn:
            rows = all_posts(conn, 200)
        # Only posts past rendering can have a deck on disk; limit the lookups.
        decks = {p["id"]: len(carousel_slides(p["id"])) for p in rows
                 if p["status"] in ("rendered", "approved", "exported")}
        return page(request, "posts.html", active="posts", posts=rows,
                    decks=decks, today=date.today().isoformat())

    @app.get("/posts/{post_id}/carousel", response_class=HTMLResponse)
    def post_carousel(request: Request, post_id: int):
        from ..review.queue import carousel_slides
        from ..store import get_post

        with connect() as conn:
            post = get_post(conn, post_id)
        if not post:
            return _redirect("/posts", err="post not found")
        slides = carousel_slides(post_id)
        return page(request, "carousel.html", active="posts",
                    post=post, slides=slides)

    @app.post("/posts/{post_id}/render")
    def post_render(post_id: int):
        jid = jobs.enqueue_job("render_post", {"post_id": post_id},
                               f"render post {post_id}")
        return _redirect(f"/jobs/{jid}")

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
        where = request.headers.get("referer", "/posts")
        where = "/schedule" if "/schedule" in where else "/posts"
        try:
            posts_service.schedule_post(post_id, when)
        except ValueError:
            return _redirect(where, err="post not found")
        return _redirect(where, msg=(f"post {post_id} scheduled for {when}" if when
                                     else f"post {post_id} schedule cleared"))

    # --- Schedule (future-posts queue) -------------------------------------
    @app.get("/schedule", response_class=HTMLResponse)
    def schedule(request: Request):
        from ..store import scheduled_posts

        today = date.today().isoformat()
        with connect() as conn:
            rows = scheduled_posts(conn)
        due = [p for p in rows if p["status"] == "approved" and (p["scheduled_for"] or "") <= today]
        return page(request, "schedule.html", active="schedule",
                    posts=rows, due=due, today=today)

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

    # --- Threads (content memory) ------------------------------------------
    @app.get("/threads", response_class=HTMLResponse)
    def threads(request: Request):
        from ..store import threads_with_posts

        with connect() as conn:
            rows = threads_with_posts(conn)
        return page(request, "threads.html", active="threads", threads=rows)

    # --- Runs history ------------------------------------------------------
    @app.get("/runs", response_class=HTMLResponse)
    def runs(request: Request):
        from ..store.runs import recent_runs

        with connect() as conn:
            rows = recent_runs(conn, 50)
        return page(request, "runs.html", active="runs", runs=rows)

    # --- Settings ----------------------------------------------------------
    @app.get("/settings", response_class=HTMLResponse)
    def settings_view(request: Request):
        cfg = config.settings()
        return page(request, "settings.html", active="settings",
                    status=auth.status(), cfg=cfg,
                    audio_mode=(cfg.get("audio", {}) or {}).get("mode", "silent"),
                    platforms=cfg.get("platforms", []),
                    posts_per_day=cfg.get("posts_per_day", 3),
                    cli_model=(cfg.get("model", {}) or {}).get("cli_model", "sonnet"),
                    api_model=(cfg.get("model", {}) or {}).get("name", "claude-sonnet-4-6"))

    @app.post("/settings/api-key")
    async def settings_api_key(request: Request):
        key = (await _form(request)).get("api_key", "").strip()
        try:
            auth.save_api_key(key)
            settings_io.set_backend("api")
        except ValueError as exc:
            return _redirect("/settings", err=str(exc))
        return _redirect("/settings", msg="API key saved; backend switched to api")

    @app.post("/settings/api-key/clear")
    def settings_api_key_clear():
        auth.clear_api_key()
        return _redirect("/settings", msg="API key removed")

    @app.post("/settings/backend")
    async def settings_backend(request: Request):
        backend = (await _form(request)).get("backend", "claude_cli")
        try:
            settings_io.set_backend(backend)
        except ValueError as exc:
            return _redirect("/settings", err=str(exc))
        return _redirect("/settings", msg=f"backend set to {backend}")

    @app.post("/settings/general")
    async def settings_general(request: Request):
        f = await _form(request)
        updates: dict = {}
        if f.get("posts_per_day"):
            try:
                updates["posts_per_day"] = max(1, int(f["posts_per_day"]))
            except ValueError:
                return _redirect("/settings", err="posts_per_day must be a number")
        if f.get("audio_mode"):
            updates["audio"] = {"mode": f["audio_mode"]}
        if f.get("platforms"):
            plats = [p.strip() for p in f["platforms"].split(",") if p.strip()]
            if plats:
                updates["platforms"] = plats
        if updates:
            settings_io.update(updates)
        return _redirect("/settings", msg="settings saved")

    return app
