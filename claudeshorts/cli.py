"""Typer CLI entrypoint for the claudeshorts pipeline.

Phase 0 wires up the command surface and a working ``init-db``. The remaining
commands are stubs that later phases fill in:
    ingest   (Phase 1)   generate (Phase 2)   render (Phase 3)
    serve    (Phase 4)   run      (Phase 5)
"""

from __future__ import annotations

import typer
from dotenv import load_dotenv

from . import __version__
from . import logging_setup
from .config import DB_PATH
from .services import pipeline_service
from .store import init_db

# Load .env (e.g. ANTHROPIC_API_KEY) before any command runs.
load_dotenv()

app = typer.Typer(
    help="Automated tech/AI news -> short-form video/slideshow pipeline.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _main() -> None:
    logging_setup.configure_logging()


@app.command("init-db")
def init_db_cmd() -> None:
    """Create the SQLite schema (idempotent)."""
    init_db()
    typer.echo("Database schema initialized.")


@app.command("ingest")
def ingest_cmd(
    since: str = typer.Option(None, help="ISO timestamp lower bound (overrides config window)."),
    limit: int = typer.Option(None, help="Max items per source."),
) -> None:
    """Fetch + dedupe news into the store. [Phase 1]"""
    init_db()
    stats = pipeline_service.run_ingest_service(since=since, limit=limit)
    typer.echo(
        f"fetched={stats['fetched']} stored={stats['stored']} "
        f"duplicates={stats['duplicates']} skipped_old={stats['skipped_old']} "
        f"total_items={stats['total_items']}"
    )
    for name, info in stats["by_source"].items():
        if "error" in info:
            typer.echo(f"  {name}: ERROR {info['error']}", err=True)
        else:
            typer.echo(f"  {name}: fetched={info['fetched']} stored={info['stored']}")


@app.command("select")
def select_cmd(
    limit: int = typer.Option(None, help="Max topics to select (default: posts_per_day)."),
) -> None:
    """Pick the day's topics, deduping and detecting follow-ups. [Phase 2]"""
    from .generate import select_topics

    init_db()
    topics = select_topics(limit=limit)
    if not topics:
        typer.echo("No fresh, un-posted topics available.")
        return
    for t in topics:
        item = t["item"]
        tag = " [follow-up]" if t["follow_up_thread"] else ""
        typer.echo(f"[{t['score']:.2f}] ({item['source']}) {item['title']}{tag}")


@app.command("generate")
def generate_cmd(
    limit: int = typer.Option(None, help="Max posts to generate, 1-20 (default: posts_per_day)."),
) -> None:
    """Turn selected topics into slides + captions via Claude (batch up to 20). [Phase 2]"""
    from rich.markup import escape
    from rich.progress import (
        BarColumn, MofNCompleteColumn, Progress, SpinnerColumn,
        TextColumn, TimeElapsedColumn,
    )

    init_db()
    tally = {"fail": 0}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Selecting topics…", total=None)

        def cb(event: str, idx: int, total: int, title: str, error) -> None:
            if progress.tasks[task].total is None:
                progress.update(task, total=total)
            short = escape(title if len(title) <= 47 else title[:46] + "…")
            if event == "start":
                progress.update(task, description=f"[{idx}/{total}] {short}")
            elif event == "ok":
                progress.update(task, description=f"[green]✓[/] {short}", advance=1)
            elif event == "fail":
                tally["fail"] += 1
                progress.update(task, description=f"[red]✗[/] {short}", advance=1)

        results = pipeline_service.run_generate_service(limit=limit, on_progress=cb)
        if progress.tasks[task].total is None:  # no topics -> no callbacks fired
            progress.update(task, total=0)

    if not results and not tally["fail"]:
        typer.echo("Nothing to generate (no fresh topics).")
        return
    typer.echo(f"\ngenerated={len(results)} failed={tally['fail']}")
    for r in results:
        tag = " [follow-up]" if r["follow_up"] else ""
        typer.echo(f"  post #{r['post_id']} ({r['thread_slug']}): {r['title']}{tag}")


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
    typer.echo(
        f"rendered post #{post_id}: {summary['frames']} frames, "
        f"{summary['duration_ms']}ms, audio={summary['audio_mode']}"
    )
    typer.echo(f"review folder: {summary['review_dir']}")


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
) -> None:
    """Run the local operator dashboard (review, articles, schedule, settings)."""
    import uvicorn

    from .dashboard import create_app

    init_db()
    typer.echo(f"Dashboard on http://{host}:{port}")
    uvicorn.run(create_app(), host=host, port=port)


@app.command("run")
def run_cmd(
    limit: int = typer.Option(None, help="Max posts (default: posts_per_day)."),
    force: bool = typer.Option(False, help="Run again even if today already completed."),
    skip_render: bool = typer.Option(False, help="Stop after generation (no render)."),
) -> None:
    """Run the full daily pipeline (ingest -> ... -> review queue). [Phase 5]"""
    summary = pipeline_service.run_full_pipeline_service(limit=limit, force=force, skip_render=skip_render)
    if summary.get("skipped"):
        typer.echo(f"Skipped: {summary['reason']} ({summary['date']}). Use --force to repeat.")
        return
    typer.echo(
        f"Run {summary['date']}: generated={len(summary.get('generated', []))} "
        f"follow_ups={len(summary.get('follow_ups', []))} "
        f"rendered={len(summary.get('rendered', []))}"
    )
    typer.echo("Review at: claudeshorts serve")


@app.command("version")
def version_cmd() -> None:
    """Print the version and db path."""
    typer.echo(f"claudeshorts {__version__}")
    typer.echo(f"db: {DB_PATH}")


def _not_yet(name: str, phase: str) -> int:
    typer.echo(f"`{name}` is not implemented yet ({phase}).", err=True)
    return 1


if __name__ == "__main__":
    app()
