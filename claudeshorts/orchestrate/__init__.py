"""Orchestration: the idempotent daily runner that ties the pipeline together.

Public entrypoint: ``run_pipeline``. Scheduling units live in ``deploy/``.
"""

from .runner import run_pipeline

__all__ = ["run_pipeline"]
