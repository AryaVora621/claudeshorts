"""Maps services.* exceptions to HTTP status codes, in one place, so every
route handler stays a one-line adapter instead of repeating try/except."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from fastapi import HTTPException

T = TypeVar("T")


def service_call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(409, str(exc)) from exc
