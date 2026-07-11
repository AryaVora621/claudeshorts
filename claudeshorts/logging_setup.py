"""One place every entry point (CLI, dashboard, job worker, scheduler)
calls to set up logging. Provides job_id/worker_id/platform as structured
fields on every record via contextvars, so goal.md's "structured logs"
requirement doesn't need every call site to pass extra= manually.
"""

from __future__ import annotations

import contextvars
import json
import logging
from contextlib import contextmanager
from typing import Iterator

from .config import settings

_job_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("job_id", default=None)
_worker_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("worker_id", default=None)
_platform: contextvars.ContextVar[str | None] = contextvars.ContextVar("platform", default=None)


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.job_id = _job_id.get()
        record.worker_id = _worker_id.get()
        record.platform = _platform.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "job_id": getattr(record, "job_id", None),
            "worker_id": getattr(record, "worker_id", None),
            "platform": getattr(record, "platform", None),
        })


_TEXT_FORMAT = (
    "%(asctime)s %(levelname)s [job=%(job_id)s worker=%(worker_id)s "
    "platform=%(platform)s] %(name)s: %(message)s"
)


@contextmanager
def bind(*, job_id: int | None = None, worker_id: str | None = None,
          platform: str | None = None) -> Iterator[None]:
    tokens = []
    if job_id is not None:
        tokens.append((_job_id, _job_id.set(job_id)))
    if worker_id is not None:
        tokens.append((_worker_id, _worker_id.set(worker_id)))
    if platform is not None:
        tokens.append((_platform, _platform.set(platform)))
    try:
        yield
    finally:
        for var, token in tokens:
            var.reset(token)


def configure_logging(level: int | str = logging.INFO, *, fmt: str | None = None) -> None:
    logger = logging.getLogger("claudeshorts")
    if getattr(logger, "_claudeshorts_configured", False):
        return
    cfg = settings().get("logging", {})
    fmt = fmt or cfg.get("format", "text")
    level = cfg.get("level", level)
    handler = logging.StreamHandler()
    handler.addFilter(_ContextFilter())
    handler.setFormatter(_JsonFormatter() if fmt == "json" else logging.Formatter(_TEXT_FORMAT, "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger._claudeshorts_configured = True
