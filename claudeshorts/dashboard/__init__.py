"""Local operator dashboard for the claudeshorts pipeline.

A server-rendered FastAPI console over local state (SQLite + review/publish
folders): run the pipeline, review/approve renders, browse and manually
ingest/generate articles, schedule future posts, inspect content-memory
threads and run history, and connect your Anthropic account.

Public entrypoint: ``create_app``.
"""

from .app import create_app

__all__ = ["create_app"]
