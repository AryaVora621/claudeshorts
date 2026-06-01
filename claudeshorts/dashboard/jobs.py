"""In-process background jobs with live log capture.

Pipeline actions (ingest / generate / render / full run) are slow and chatty, so
the dashboard runs them on a daemon thread and streams their log lines to the
browser over Server-Sent Events. A logging handler attached to the
``claudeshorts`` logger fans records out to whichever job owns the current
thread, so existing ``log.info(...)`` calls light up the UI for free.

This is deliberately memory-only: jobs are operator actions during a session,
not durable state (that lives in SQLite). Restarting the server clears them.
"""

from __future__ import annotations

import itertools
import logging
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, Iterator

_counter = itertools.count(1)
_jobs: dict[int, "Job"] = {}
_lock = threading.Lock()
# thread ident -> job id, so the log handler can route records to the right job.
_thread_job: dict[int, int] = {}


@dataclass
class Job:
    id: int
    name: str
    status: str = "running"  # running | ok | error
    lines: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None
    _cv: threading.Condition = field(default_factory=threading.Condition, repr=False)

    def append(self, line: str) -> None:
        with self._cv:
            self.lines.append(line)
            self._cv.notify_all()

    def finish(self, status: str, error: str | None = None) -> None:
        with self._cv:
            self.status = status
            self.error = error
            self.finished_at = time.time()
            self._cv.notify_all()

    @property
    def done(self) -> bool:
        return self.finished_at is not None


class _JobLogHandler(logging.Handler):
    """Routes a log record to the job owning the emitting thread, if any."""

    def emit(self, record: logging.LogRecord) -> None:
        job_id = _thread_job.get(threading.get_ident())
        if job_id is None:
            return
        job = _jobs.get(job_id)
        if job is not None:
            try:
                job.append(self.format(record))
            except Exception:  # never let logging crash a job
                pass


_handler = _JobLogHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))


def _install_handler() -> None:
    lg = logging.getLogger("claudeshorts")
    lg.setLevel(logging.INFO)
    if not any(isinstance(h, _JobLogHandler) for h in lg.handlers):
        lg.addHandler(_handler)


def start_job(name: str, target: Callable[[], object]) -> int:
    """Run ``target`` on a daemon thread; return the new job id immediately."""
    _install_handler()
    job = Job(id=next(_counter), name=name)
    with _lock:
        _jobs[job.id] = job

    def _run() -> None:
        _thread_job[threading.get_ident()] = job.id
        job.append(f"▶ {name} started")
        try:
            result = target()
            if result is not None:
                job.append(str(result))
            job.append(f"✔ {name} complete")
            job.finish("ok")
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            job.append(f"✖ {name} failed: {exc}")
            job.append(traceback.format_exc())
            job.finish("error", str(exc))
        finally:
            _thread_job.pop(threading.get_ident(), None)

    threading.Thread(target=_run, name=f"job-{job.id}", daemon=True).start()
    return job.id


def get_job(job_id: int) -> Job | None:
    return _jobs.get(job_id)


def recent_jobs(limit: int = 15) -> list[Job]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j.id, reverse=True)[:limit]


def stream(job_id: int) -> Iterator[str]:
    """Yield SSE-formatted lines for a job until it finishes."""
    job = _jobs.get(job_id)
    if job is None:
        yield "event: done\ndata: missing\n\n"
        return
    idx = 0
    while True:
        with job._cv:
            while idx >= len(job.lines) and not job.done:
                job._cv.wait(timeout=1.0)
            new = job.lines[idx:]
            idx = len(job.lines)
            finished = job.done and idx >= len(job.lines)
        for line in new:
            # SSE: encode newlines within a record as separate data: lines.
            payload = "\n".join(f"data: {part}" for part in line.splitlines() or [""])
            yield payload + "\n\n"
        if finished:
            yield f"event: done\ndata: {job.status}\n\n"
            return
