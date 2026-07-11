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
