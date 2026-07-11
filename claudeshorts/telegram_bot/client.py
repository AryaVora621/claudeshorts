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
