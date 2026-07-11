from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..services import posts_service
from .errors import service_call
from .schemas import ApproveResponse, PostIdResponse, RejectRequest, ScheduleRequest, ScheduleResponse

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("")
def list_posts(limit: int = 200) -> list[dict[str, Any]]:
    return service_call(posts_service.list_posts, limit)


@router.get("/{post_id}")
def get_post_route(post_id: int) -> dict[str, Any]:
    return service_call(posts_service.get_post, post_id)


@router.post("/{post_id}/approve", response_model=ApproveResponse)
def approve(post_id: int) -> dict[str, Any]:
    return service_call(posts_service.approve_post, post_id)


@router.post("/{post_id}/reject", response_model=PostIdResponse)
def reject(post_id: int, body: RejectRequest) -> dict[str, Any]:
    return service_call(posts_service.reject_post, post_id, note=body.note)


@router.post("/{post_id}/schedule", response_model=ScheduleResponse)
def schedule(post_id: int, body: ScheduleRequest) -> dict[str, Any]:
    return service_call(posts_service.schedule_post, post_id, body.scheduled_for)


@router.post("/{post_id}/export", response_model=PostIdResponse)
def export_now(post_id: int) -> dict[str, Any]:
    return service_call(posts_service.export_post_now, post_id)
