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

from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse, HTMLResponse, RedirectResponse, StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import config
from ..store import connect
from . import auth, jobs, settings_io

_HERE = Path(__file__).resolve().parent
_templates = Jinja2Templates(directory=str(_HERE / "templates"))


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
    """Locate a post's rendered media in the review folder (any date)."""
    from ..review.queue import review_dir_for

    d = review_dir_for(post_id)
    path = d / name
    if path.exists():
        return path
    matches = sorted(config.REVIEW_DIR.glob(f"*/post_{post_id}/{name}"))
    return matches[-1] if matches else None


def create_app() -> FastAPI:
    app = FastAPI(title="claudeshorts dashboard")
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

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
            from ..orchestrate import run_pipeline
            jid = jobs.start_job("daily run", lambda: run_pipeline(force=True))
        elif name == "ingest":
            from ..ingest import run_ingest
            jid = jobs.start_job("ingest", run_ingest)
        elif name == "generate":
            from ..generate import run_generate
            jid = jobs.start_job("generate", lambda: run_generate())
        else:
            return _redirect("/", err=f"unknown action {name}")
        return _redirect(f"/jobs/{jid}")

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_detail(request: Request, job_id: int):
        job = jobs.get_job(job_id)
        if not job:
            return _redirect("/", err="no such job")
        return page(request, "job.html", active="", job=job)

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
        from ..review.queue import pending_reviews
        from ..review.captions import PLATFORM_CAPTION

        posts = pending_reviews()
        caps = {p["id"]: {pl: fn(p.get("captions") or {})
                          for pl, fn in PLATFORM_CAPTION.items()} for p in posts}
        return page(request, "review.html", active="review", posts=posts, caps=caps)

    @app.get("/media/{post_id}/{name}")
    def media(post_id: int, name: str):
        if name not in ("video.mp4", "thumb.png"):
            return HTMLResponse("not found", status_code=404)
        path = _media_path(post_id, name)
        if not path:
            return HTMLResponse("not found", status_code=404)
        return FileResponse(path)

    @app.post("/posts/{post_id}/approve")
    def approve(post_id: int):
        from ..publish import export_post
        from ..store import get_post, set_status

        with connect() as conn:
            post = get_post(conn, post_id)
        if post:
            with connect() as conn:
                set_status(conn, post_id, "approved")
                conn.commit()
            # No schedule -> publish immediately; scheduled -> the run drains it.
            if not post.get("scheduled_for"):
                try:
                    export_post(post)
                except FileNotFoundError as exc:
                    return _redirect("/review", err=str(exc))
                return _redirect("/review", msg=f"post {post_id} approved & exported")
            return _redirect("/review",
                             msg=f"post {post_id} approved; will publish {post['scheduled_for']}")
        return _redirect("/review", err="post not found")

    @app.post("/posts/{post_id}/reject")
    async def reject(post_id: int, request: Request):
        from ..store import set_status

        note = (await _form(request)).get("note", "").strip() or None
        with connect() as conn:
            set_status(conn, post_id, "rejected", note=note)
            conn.commit()
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
        from ..store import insert_manual_item
        from ..store.pins import pin_item

        f = await _form(request)
        title = (f.get("title") or "").strip()
        if not title:
            return _redirect("/articles", err="title is required")
        with connect() as conn:
            item_id, created = insert_manual_item(
                conn, title=title,
                url=(f.get("url") or "").strip() or None,
                summary=(f.get("summary") or "").strip() or None,
            )
            conn.commit()
        action = f.get("action", "pin")
        if action == "generate":
            from ..generate import generate_for_item
            jid = jobs.start_job(f"generate from “{title[:40]}”",
                                 lambda: generate_for_item(item_id))
            return _redirect(f"/jobs/{jid}")
        with connect() as conn:
            pin_item(conn, item_id)
            conn.commit()
        verb = "added" if created else "already known; pinned"
        return _redirect("/articles", msg=f"article {verb} (#{item_id})")

    @app.post("/articles/{item_id}/generate")
    def articles_generate(item_id: int):
        from ..generate import generate_for_item

        jid = jobs.start_job(f"generate from item {item_id}",
                             lambda: generate_for_item(item_id))
        return _redirect(f"/jobs/{jid}")

    @app.post("/articles/{item_id}/pin")
    def articles_pin(item_id: int):
        from ..store.pins import pin_item

        with connect() as conn:
            pin_item(conn, item_id)
            conn.commit()
        return _redirect("/articles", msg=f"item {item_id} pinned for a future post")

    @app.post("/articles/{item_id}/unpin")
    def articles_unpin(item_id: int):
        from ..store.pins import unpin_item

        with connect() as conn:
            unpin_item(conn, item_id)
            conn.commit()
        return _redirect("/articles", msg=f"item {item_id} unpinned")

    # --- Posts -------------------------------------------------------------
    @app.get("/posts", response_class=HTMLResponse)
    def posts(request: Request):
        from ..store import all_posts

        with connect() as conn:
            rows = all_posts(conn, 200)
        return page(request, "posts.html", active="posts", posts=rows,
                    today=date.today().isoformat())

    @app.post("/posts/{post_id}/render")
    def post_render(post_id: int):
        def _do():
            from ..render import render_post
            from ..review import assemble_review
            from ..store import get_post

            with connect() as conn:
                post = get_post(conn, post_id)
            if not post:
                raise ValueError(f"no post {post_id}")
            result = render_post(post)
            assemble_review(post, result)
            return f"rendered post {post_id}: {result.get('frames')} frames"

        jid = jobs.start_job(f"render post {post_id}", _do)
        return _redirect(f"/jobs/{jid}")

    @app.post("/posts/{post_id}/export")
    def post_export(post_id: int):
        from ..publish import export_post
        from ..store import get_post, set_status

        with connect() as conn:
            post = get_post(conn, post_id)
        if not post:
            return _redirect("/posts", err="post not found")
        with connect() as conn:
            set_status(conn, post_id, "approved")
            conn.commit()
        try:
            export_post(post)
        except FileNotFoundError as exc:
            return _redirect("/posts", err=str(exc))
        return _redirect("/posts", msg=f"post {post_id} exported")

    @app.post("/posts/{post_id}/schedule")
    async def post_schedule(post_id: int, request: Request):
        from ..store import set_schedule

        when = (await _form(request)).get("scheduled_for", "").strip() or None
        with connect() as conn:
            set_schedule(conn, post_id, when)
            conn.commit()
        where = request.headers.get("referer", "/posts")
        where = "/schedule" if "/schedule" in where else "/posts"
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
        from ..publish import export_post
        from ..store import get_post, set_status

        with connect() as conn:
            post = get_post(conn, post_id)
        if not post:
            return _redirect("/schedule", err="post not found")
        with connect() as conn:
            set_status(conn, post_id, "approved")
            conn.commit()
        try:
            export_post(post)
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
