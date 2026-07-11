from __future__ import annotations

from fastapi import APIRouter, status

from ..jobs import queue as job_queue
from .schemas import EnqueueResponse

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/ingest", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest() -> dict[str, int]:
    return {"job_id": job_queue.enqueue("ingest", {}, name="ingest (api)")}


@router.post("/generate", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def generate() -> dict[str, int]:
    return {"job_id": job_queue.enqueue("generate", {}, name="generate (api)")}


@router.post(
    "/render/{post_id}", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED,
)
def render(post_id: int) -> dict[str, int]:
    job_id = job_queue.enqueue(
        "render_post", {"post_id": post_id}, name=f"render post {post_id} (api)"
    )
    return {"job_id": job_id}


@router.post("/run", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def run() -> dict[str, int]:
    return {"job_id": job_queue.enqueue("full_run", {}, name="daily run (api)")}
