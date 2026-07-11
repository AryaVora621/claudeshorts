from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..services import articles_service
from ..store import connect, latest_items
from .schemas import AddArticleRequest, EnqueueResponse

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("")
def list_articles(limit: int = 120) -> list[dict[str, Any]]:
    with connect() as conn:
        return latest_items(conn, limit)


@router.post("")
def add_article(body: AddArticleRequest) -> dict[str, Any]:
    return articles_service.add_manual_article(
        title=body.title, url=body.url, summary=body.summary, action=body.action,
    )


@router.post("/{item_id}/pin")
def pin(item_id: int) -> dict[str, Any]:
    return articles_service.pin_article(item_id)


@router.post("/{item_id}/unpin")
def unpin(item_id: int) -> dict[str, Any]:
    return articles_service.unpin_article(item_id)


@router.post("/{item_id}/generate", response_model=EnqueueResponse)
def generate(item_id: int) -> dict[str, Any]:
    return articles_service.generate_from_item(item_id)
