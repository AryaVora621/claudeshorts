from __future__ import annotations

from datetime import timedelta

from claudeshorts.jobs import queue


def test_backoff_doubles_then_caps():
    assert queue.backoff(1) == timedelta(seconds=5)
    assert queue.backoff(2) == timedelta(seconds=10)
    assert queue.backoff(3) == timedelta(seconds=20)
    assert queue.backoff(10) == timedelta(seconds=300)
