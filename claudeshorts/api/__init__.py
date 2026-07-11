"""REST API over claudeshorts services (goal.md: backend never depends on
any frontend — this is one more client of `services/`, same as the CLI and
dashboard)."""

from __future__ import annotations

from fastapi import APIRouter

from . import health, posts

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(posts.router)
