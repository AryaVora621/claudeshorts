"""News ingestion: fetch from configured sources, normalize, dedupe, store.

Public entrypoint: ``run_ingest``.
"""

from .runner import run_ingest

__all__ = ["run_ingest"]
