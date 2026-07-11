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


def _raise_for_blocked_transition(job_id: int) -> None:
    """The queue call matched zero rows: figure out why and raise the right
    HTTP error. Either the job doesn't exist (404) or it exists but its
    current status blocks the transition (409, e.g. cancelling a job that's
    already COMPLETED)."""
    with connect() as conn:
        row = store_jobs.get_job(conn, job_id)
    if not row:
        raise HTTPException(404, f"job {job_id} not found")
    raise HTTPException(409, f"job {job_id} is {row['status']}")


@router.post("/{job_id}/cancel")
def cancel(job_id: int) -> dict[str, Any]:
    if not job_queue.request_cancel(job_id):
        _raise_for_blocked_transition(job_id)
    return {"job_id": job_id}


@router.post("/{job_id}/pause")
def pause(job_id: int) -> dict[str, Any]:
    if not job_queue.request_pause(job_id):
        _raise_for_blocked_transition(job_id)
    return {"job_id": job_id}


@router.post("/{job_id}/resume")
def resume(job_id: int) -> dict[str, Any]:
    if not job_queue.resume(job_id):
        _raise_for_blocked_transition(job_id)
    return {"job_id": job_id}


@router.post("/{job_id}/retry")
def retry(job_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = store_jobs.get_job(conn, job_id)
    if not row:
        raise HTTPException(404, f"job {job_id} not found")
    if row["status"] != "FAILED":
        raise HTTPException(409, f"job {job_id} is not failed (status={row['status']})")
    new_id = job_queue.enqueue(row["job_type"], row["payload"], name=row["name"])
    return {"job_id": new_id}
