"""Incremental window planning: where each source resumes from its checkpoint."""

from datetime import date, datetime, timezone

from src.config import load_config
from src.pipeline import incremental_plan

SOURCES = load_config().sources
BACKFILL_START = date(2026, 8, 15)
TODAY = date(2026, 11, 15)


def test_no_checkpoint_falls_back_to_backfill_range():
    for name in ("open_meteo", "openaq", "usgs"):
        start, end, after = incremental_plan(name, SOURCES, BACKFILL_START, TODAY, None)
        assert (start, end, after) == (BACKFILL_START, TODAY, None)


def test_open_meteo_restarts_seven_days_before_watermark():
    wm = datetime(2026, 11, 14, 23, tzinfo=timezone.utc)
    start, end, after = incremental_plan("open_meteo", SOURCES, BACKFILL_START, TODAY, wm)
    assert start == date(2026, 11, 7)
    assert end == TODAY
    assert after is None


def test_openaq_restarts_48_hours_before_watermark():
    wm = datetime(2026, 11, 15, 0, tzinfo=timezone.utc)
    start, _, after = incremental_plan("openaq", SOURCES, BACKFILL_START, TODAY, wm)
    assert start == date(2026, 11, 13)
    assert after is None


def test_usgs_keeps_full_range_and_uses_updatedafter_24_hours_back():
    wm = datetime(2026, 11, 15, 11, tzinfo=timezone.utc)
    start, end, after = incremental_plan("usgs", SOURCES, BACKFILL_START, TODAY, wm)
    assert (start, end) == (BACKFILL_START, TODAY)
    assert after == datetime(2026, 11, 14, 11, tzinfo=timezone.utc)
