"""Lightweight, optional progress reporting for long-running pipeline steps.

The pipeline (ingest / generate / render / publish) reports two levels of
progress so a UI can draw bars:

- ``phase(index, total, label)``  which stage of a multi-stage run we are in.
- ``step(current, total, label)`` progress within the current stage (post M of
  N, frame M of N). ``total == 0`` means "indeterminate" (unknown length).

Reporting is delivered to a per-thread *sink* so the caller stays decoupled from
any particular consumer. The dashboard installs a sink on each job's worker
thread; the CLI could install one that drives a rich bar. When no sink is set
(plain library use, tests) every call is a cheap no-op, so the pipeline can call
these freely without knowing who, if anyone, is listening.

This module deliberately depends on nothing else in the package: the pipeline
imports it, never the other way around, which keeps the dashboard a consumer of
the core rather than a dependency of it.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

# A sink receives (kind, payload) where kind is "phase" or "step". Keyed by the
# worker thread's ident, mirroring how the dashboard's log handler already routes
# records to the job that owns a thread.
Sink = Callable[[str, dict[str, Any]], None]
_sinks: dict[int, Sink] = {}


def set_sink(sink: Sink) -> None:
    """Route progress emitted on the current thread to ``sink``."""
    _sinks[threading.get_ident()] = sink


def clear_sink() -> None:
    """Stop routing progress on the current thread (safe if none was set)."""
    _sinks.pop(threading.get_ident(), None)


def _emit(kind: str, payload: dict[str, Any]) -> None:
    sink = _sinks.get(threading.get_ident())
    if sink is None:
        return
    try:
        sink(kind, payload)
    except Exception:  # never let progress reporting break the actual work
        pass


def phase(index: int, total: int, label: str = "") -> None:
    """Report the current stage of a multi-stage run (1-based ``index``)."""
    _emit("phase", {"index": int(index), "total": int(total), "label": label})


def step(current: int, total: int, label: str = "") -> None:
    """Report progress within the current stage. ``total == 0`` = indeterminate."""
    _emit("step", {"current": int(current), "total": int(total), "label": label})


def reset_step(label: str = "") -> None:
    """Clear the per-item bar (e.g. between phases) back to indeterminate."""
    _emit("step", {"current": 0, "total": 0, "label": label})
