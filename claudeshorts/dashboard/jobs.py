"""In-process background jobs with live log capture, progress, and persistence.

Pipeline actions (ingest / generate / render / full run) are slow and chatty, so
the dashboard runs them on a daemon thread and streams their log lines to the
browser over Server-Sent Events. A logging handler attached to the
``claudeshorts`` logger fans records out to whichever job owns the current
thread, so existing ``log.info(...)`` calls light up the UI for free. Each job
also installs a :mod:`claudeshorts.progress` sink on its worker thread, so the
pipeline's ``phase``/``step`` calls drive the dashboard's bars.

Jobs stay in memory while they run (that is the live source for streaming), and a
snapshot is mirrored to SQLite (the ``jobs`` table) so the operator can click
back onto a past job after the server restarts. On first use we mark any row
left ``running`` by a dead process as ``interrupted`` and continue the id counter
past the persisted maximum.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from .. import progress
from ..store import connect
from ..store import jobs as store_jobs

_jobs: dict[int, "Job"] = {}
_lock = threading.Lock()
# thread ident -> job id, so the log handler can route records to the right job.
_thread_job: dict[int, int] = {}

_inited = False
_next_id = 1
# Persist a running job's snapshot at most this often (seconds); finish + phase
# changes always flush so the durable record stays close to reality.
_PERSIST_EVERY = 1.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso_to_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


@dataclass
class Job:
    id: int
    name: str
    status: str = "running"  # running | ok | error | interrupted
    lines: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None
    # Two-level progress (see claudeshorts.progress). total == 0 = indeterminate.
    phase_index: int = 0
    phase_total: int = 0
    phase_label: str = ""
    progress_current: int = 0
    progress_total: int = 0
    progress_label: str = ""
    # Reconstructed from the DB (a finished/interrupted job from a prior run):
    # read-only, never streamed live.
    persisted: bool = False
    _cv: threading.Condition = field(default_factory=threading.Condition, repr=False)
    _last_persist: float = 0.0

    # --- mutation (called on the worker thread) ----------------------------
    def append(self, line: str) -> None:
        with self._cv:
            self.lines.append(line)
            self._cv.notify_all()
        self._maybe_persist()

    def set_phase(self, index: int, total: int, label: str) -> None:
        with self._cv:
            self.phase_index, self.phase_total, self.phase_label = index, total, label
            # A new phase resets the per-item bar until the phase reports a step.
            self.progress_current = self.progress_total = 0
            self.progress_label = ""
            self._cv.notify_all()
        self._maybe_persist(force=True)  # phases are rare; keep the record fresh

    def set_step(self, current: int, total: int, label: str) -> None:
        with self._cv:
            self.progress_current, self.progress_total = current, total
            self.progress_label = label
            self._cv.notify_all()
        self._maybe_persist()

    def finish(self, status: str, error: str | None = None) -> None:
        with self._cv:
            self.status = status
            self.error = error
            self.finished_at = time.time()
            self._cv.notify_all()
        self._maybe_persist(force=True)

    @property
    def done(self) -> bool:
        return self.finished_at is not None

    # --- progress signature (lets the SSE stream detect changes) -----------
    def _progress_sig(self) -> tuple:
        return (self.phase_index, self.phase_total, self.phase_label,
                self.progress_current, self.progress_total, self.progress_label)

    # --- persistence -------------------------------------------------------
    def _snapshot(self) -> dict[str, Any]:
        with self._cv:
            return {
                "status": self.status,
                "phase_index": self.phase_index,
                "phase_total": self.phase_total,
                "phase_label": self.phase_label,
                "progress_current": self.progress_current,
                "progress_total": self.progress_total,
                "progress_label": self.progress_label,
                "log": "\n".join(self.lines),
                "error": self.error,
                "finished_at": (_now_iso() if self.finished_at else None),
            }

    def _maybe_persist(self, *, force: bool = False) -> None:
        if self.persisted:  # a DB-reconstructed job is read-only
            return
        now = time.monotonic()
        if not force and now - self._last_persist < _PERSIST_EVERY:
            return
        self._last_persist = now
        try:
            with connect() as conn:
                store_jobs.save_snapshot(conn, self.id, self._snapshot())
        except Exception:  # durability is best-effort; never break a running job
            pass

    # --- view model --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        with self._cv:
            phase_pct = (round(100 * self.phase_index / self.phase_total)
                         if self.phase_total else None)
            step_pct = (round(100 * self.progress_current / self.progress_total)
                        if self.progress_total else None)
            end = self.finished_at or time.time()
            return {
                "id": self.id,
                "name": self.name,
                "status": self.status,
                "done": self.done,
                "phase": {"index": self.phase_index, "total": self.phase_total,
                          "label": self.phase_label, "percent": phase_pct},
                "step": {"current": self.progress_current, "total": self.progress_total,
                         "label": self.progress_label, "percent": step_pct},
                "started_at": datetime.fromtimestamp(
                    self.started_at, timezone.utc).isoformat(timespec="seconds"),
                "elapsed_seconds": round(max(0.0, end - self.started_at), 1),
                "error": self.error,
            }


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


def _ensure_init() -> None:
    """Mark orphaned jobs interrupted and seed the id counter from the DB. Once."""
    global _inited, _next_id
    if _inited:
        return
    with _lock:
        if _inited:
            return
        try:
            with connect() as conn:
                store_jobs.mark_running_interrupted(conn)
                _next_id = store_jobs.max_id(conn) + 1
        except Exception:  # a fresh/missing db just means we start clean
            _next_id = 1
        _inited = True


def _job_from_row(row: dict[str, Any]) -> Job:
    """Reconstruct a read-only Job from a persisted row (history after restart)."""
    status = row["status"]
    started = _iso_to_epoch(row.get("started_at")) or time.time()
    finished = _iso_to_epoch(row.get("finished_at"))
    job = Job(
        id=row["id"], name=row["name"], status=status,
        lines=(row.get("log") or "").split("\n") if row.get("log") else [],
        started_at=started,
        finished_at=finished if status != "running" else None,
        error=row.get("error"),
        phase_index=row.get("phase_index", 0), phase_total=row.get("phase_total", 0),
        phase_label=row.get("phase_label", "") or "",
        progress_current=row.get("progress_current", 0),
        progress_total=row.get("progress_total", 0),
        progress_label=row.get("progress_label", "") or "",
        persisted=True,
    )
    # A reconstructed job is never live, so make sure it reads as finished.
    if job.finished_at is None:
        job.finished_at = started
    return job


def start_job(name: str, target: Callable[[], object]) -> int:
    """Run ``target`` on a daemon thread; return the new job id immediately."""
    _ensure_init()
    _install_handler()
    global _next_id
    with _lock:
        job_id = _next_id
        _next_id += 1
        job = Job(id=job_id, name=name)
        _jobs[job_id] = job
    try:
        with connect() as conn:
            store_jobs.insert_job(conn, job_id=job_id, name=name)
    except Exception:
        pass

    def _run() -> None:
        ident = threading.get_ident()
        _thread_job[ident] = job.id
        progress.set_sink(_sink_for(job))
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
            progress.clear_sink()
            _thread_job.pop(ident, None)

    threading.Thread(target=_run, name=f"job-{job.id}", daemon=True).start()
    return job.id


def _sink_for(job: "Job") -> Callable[[str, dict[str, Any]], None]:
    """Build the progress sink that maps pipeline progress onto ``job``."""

    def sink(kind: str, payload: dict[str, Any]) -> None:
        if kind == "phase":
            job.set_phase(payload["index"], payload["total"], payload.get("label", ""))
        elif kind == "step":
            job.set_step(payload["current"], payload["total"], payload.get("label", ""))

    return sink


def get_job(job_id: int) -> Job | None:
    _ensure_init()
    job = _jobs.get(job_id)
    if job is not None:
        return job
    try:
        with connect() as conn:
            row = store_jobs.get_job(conn, job_id)
    except Exception:
        row = None
    return _job_from_row(row) if row else None


def recent_jobs(limit: int = 50) -> list[Job]:
    """Most recent jobs, newest first. Live in-memory jobs override DB snapshots."""
    _ensure_init()
    try:
        with connect() as conn:
            rows = store_jobs.recent_jobs(conn, limit)
    except Exception:
        rows = []
    out: list[Job] = []
    seen: set[int] = set()
    for row in rows:
        jid = row["id"]
        out.append(_jobs.get(jid) or _job_from_row(row))
        seen.add(jid)
    # Any live job not yet flushed to the db (rare; insert happens on start).
    for jid, job in sorted(_jobs.items(), reverse=True):
        if jid not in seen:
            out.append(job)
    out.sort(key=lambda j: j.id, reverse=True)
    return out[:limit]


def stream(job_id: int) -> Iterator[str]:
    """Yield SSE for a job: log lines, ``progress`` events, then ``done``."""
    job = _jobs.get(job_id)
    if job is None:
        # Not live in this process; emit whatever the db remembers, then close.
        persisted = get_job(job_id)
        if persisted is not None:
            yield _progress_event(persisted)
            for line in persisted.lines:
                yield _data_event(line)
            yield f"event: done\ndata: {persisted.status}\n\n"
        else:
            yield "event: done\ndata: missing\n\n"
        return

    idx = 0
    last_sig = None
    yield _progress_event(job)
    last_sig = job._progress_sig()
    while True:
        with job._cv:
            while (idx >= len(job.lines)
                   and job._progress_sig() == last_sig
                   and not job.done):
                job._cv.wait(timeout=1.0)
            new = job.lines[idx:]
            idx = len(job.lines)
            sig = job._progress_sig()
            finished = job.done and idx >= len(job.lines)
        for line in new:
            yield _data_event(line)
        if sig != last_sig:
            last_sig = sig
            yield _progress_event(job)
        if finished:
            yield f"event: done\ndata: {job.status}\n\n"
            return


def _data_event(line: str) -> str:
    # SSE: encode newlines within a record as separate data: lines.
    return "\n".join(f"data: {part}" for part in line.splitlines() or [""]) + "\n\n"


def _progress_event(job: "Job") -> str:
    import json

    d = job.to_dict()
    payload = {"phase": d["phase"], "step": d["step"],
               "status": d["status"], "elapsed_seconds": d["elapsed_seconds"]}
    return f"event: progress\ndata: {json.dumps(payload)}\n\n"
