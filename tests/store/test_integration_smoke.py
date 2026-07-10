# tests/store/test_integration_smoke.py
from __future__ import annotations

import importlib


def test_all_caller_modules_import_cleanly():
    """The 8 files that call store/*.py must import without error against the
    new Postgres-backed store (no leftover sqlite3-specific assumptions)."""
    modules = [
        "claudeshorts.dashboard.app",
        "claudeshorts.dashboard.jobs",
        "claudeshorts.generate.runner",
        "claudeshorts.generate.select",
        "claudeshorts.ingest.runner",
        "claudeshorts.orchestrate.runner",
        "claudeshorts.publish.exporter",
        "claudeshorts.review.queue",
    ]
    for name in modules:
        importlib.import_module(name)
