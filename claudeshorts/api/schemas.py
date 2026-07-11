"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from pydantic import BaseModel


class ApproveResponse(BaseModel):
    post_id: int
    exported: bool
    scheduled_for: str | None


class ScheduleRequest(BaseModel):
    scheduled_for: str | None = None


class ScheduleResponse(BaseModel):
    post_id: int
    scheduled_for: str | None


class RejectRequest(BaseModel):
    note: str | None = None


class PostIdResponse(BaseModel):
    post_id: int


class AddArticleRequest(BaseModel):
    title: str
    url: str | None = None
    summary: str | None = None
    action: str = "pin"


class EnqueueResponse(BaseModel):
    job_id: int


class JobResponse(BaseModel):
    id: int
    name: str
    status: str
    job_type: str
    attempts: int
    error: str | None
