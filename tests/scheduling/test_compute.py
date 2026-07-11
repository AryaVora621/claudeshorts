from __future__ import annotations

from datetime import datetime, timezone

from claudeshorts.scheduling.compute import next_run_at


def test_daily_at_same_day_if_time_not_passed():
    after = datetime(2026, 7, 10, 6, 0, tzinfo=timezone.utc)
    got = next_run_at("daily_at", daily_at="08:00", after=after)
    assert got == datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc)


def test_daily_at_next_day_if_time_passed():
    after = datetime(2026, 7, 10, 9, 0, tzinfo=timezone.utc)
    got = next_run_at("daily_at", daily_at="08:00", after=after)
    assert got == datetime(2026, 7, 11, 8, 0, tzinfo=timezone.utc)


def test_every_minutes_adds_interval():
    after = datetime(2026, 7, 10, 6, 0, tzinfo=timezone.utc)
    got = next_run_at("every_minutes", every_minutes=60, after=after)
    assert got == datetime(2026, 7, 10, 7, 0, tzinfo=timezone.utc)


def test_daily_at_with_weekday_skips_to_target_weekday():
    # 2026-07-10 is a Friday (weekday=4); target weekday=0 (Monday)
    after = datetime(2026, 7, 10, 6, 0, tzinfo=timezone.utc)
    got = next_run_at("daily_at", daily_at="09:00", weekday=0, after=after)
    assert got == datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)


def test_daily_at_with_weekday_same_day_if_not_passed():
    # 2026-07-13 is a Monday
    after = datetime(2026, 7, 13, 6, 0, tzinfo=timezone.utc)
    got = next_run_at("daily_at", daily_at="09:00", weekday=0, after=after)
    assert got == datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
