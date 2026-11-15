"""Open-Meteo payload -> staging.weather_staging rows (one dict per city-hour)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.transform.common import parse_utc

VARIABLE_TO_COLUMN = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "relative_humidity_pct",
    "precipitation": "precipitation_mm",
    "wind_speed_10m": "wind_speed_kmh",
    "weather_code": "weather_code",
}


def location_key(city_name: str) -> str:
    return f"city:{city_name.strip().lower()}"


def to_rows(payload: dict[str, Any], city_name: str, retrieved_at: datetime) -> tuple[list[dict[str, Any]], int]:
    """Return (rows, rejected). Rows with an unparseable timestamp are rejected."""
    hourly = payload["hourly"]
    key = location_key(city_name)
    rows: list[dict[str, Any]] = []
    rejected = 0
    for i, stamp in enumerate(hourly["time"]):
        try:
            observed_at = parse_utc(stamp)
        except ValueError:
            rejected += 1
            continue
        row: dict[str, Any] = {
            "location_key": key,
            "observed_at": observed_at,
            "grid_latitude": payload.get("latitude"),
            "grid_longitude": payload.get("longitude"),
            "grid_elevation_m": payload.get("elevation"),
            "source_retrieved_at": retrieved_at,
        }
        for variable, column in VARIABLE_TO_COLUMN.items():
            values = hourly.get(variable)
            row[column] = values[i] if values is not None else None
        rows.append(row)
    return rows, rejected
