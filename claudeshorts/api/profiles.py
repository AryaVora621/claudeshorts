"""Read-only per chunk 12's confirmed scope — no endpoint to create or
log into a profile from the API; that requires a visible browser on the
host (chunk 11's interactive_login.py)."""

from __future__ import annotations

from fastapi import APIRouter

from ..browser import profiles

router = APIRouter(tags=["profiles"])


@router.get("/profiles")
def list_profiles() -> list[dict]:
    return [
        {"slug": p["slug"], "platform": p["platform"], "login_health": p["login_health"]}
        for p in profiles.list_profiles()
    ]
