"""OpenAQ hourly payload -> staging.air_quality_staging rows (one dict per sensor-hour)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.transform.common import fix_mojibake, nested_get, parse_utc

WANTED_PARAMETER = "pm25"


def location_key(location_id: int) -> str:
    return f"openaq:{location_id}"


def to_rows(
    payload: dict[str, Any], sensor_id: int, location_id: int, retrieved_at: datetime
) -> tuple[list[dict[str, Any]], int]:
    """Return (rows, rejected). Rows for other parameters are skipped, not rejected."""
    key = location_key(location_id)
    rows: list[dict[str, Any]] = []
    rejected = 0
    for item in payload["results"]:
        if nested_get(item, "parameter", "name") != WANTED_PARAMETER:
            continue
        try:
            period_start = parse_utc(nested_get(item, "period", "datetimeFrom", "utc"))
            period_end = parse_utc(nested_get(item, "period", "datetimeTo", "utc"))
        except (TypeError, ValueError):
            rejected += 1
            continue
        if period_end <= period_start:
            rejected += 1
            continue
        summary = item.get("summary") or {}
        coverage = item.get("coverage") or {}
        rows.append({
            "batch_id": None,  # filled in by the loader
            "sensor_id": sensor_id,
            "location_key": key,
            "period_start": period_start,
            "period_end": period_end,
            "parameter": WANTED_PARAMETER,
            "units": fix_mojibake(nested_get(item, "parameter", "units")),
            "value": item.get("value"),
            "min_value": summary.get("min"),
            "max_value": summary.get("max"),
            "observed_count": coverage.get("observedCount"),
            "expected_count": coverage.get("expectedCount"),
            "percent_coverage": coverage.get("percentCoverage"),
            "has_flags": bool(nested_get(item, "flagInfo", "hasFlags")),
            "source_retrieved_at": retrieved_at,
        })
    return rows, rejected
