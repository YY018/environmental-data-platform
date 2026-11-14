"""Open-Meteo historical archive extractor (hourly weather per city)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Iterable, Iterator

from src.extract.common import ExtractResult, RawStore, ValidationError, date_windows, utc_now
from src.extract.http_client import HttpClient

log = logging.getLogger(__name__)
SOURCE = "open_meteo"


def validate_payload(payload: dict[str, Any], variables: list[str]) -> int:
    """Check structure and return the number of hourly rows."""
    if payload.get("error"):
        raise ValidationError(f"Open-Meteo error: {payload.get('reason')}")
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise ValidationError("Response has no hourly.time array")
    n = len(hourly["time"])
    missing = [v for v in variables if v not in hourly]
    if missing:
        raise ValidationError(f"Response is missing variables: {missing}")
    uneven = [v for v in variables if len(hourly[v]) != n]
    if uneven:
        raise ValidationError(f"Arrays not aligned with time for: {uneven}")
    if payload.get("utc_offset_seconds") != 0:
        raise ValidationError("Expected UTC timestamps (utc_offset_seconds == 0)")
    return n


def extract(
    client: HttpClient,
    raw_store: RawStore,
    source_cfg: dict[str, Any],
    start: date,
    end: date,
    locations: Iterable[dict[str, Any]] | None = None,
) -> Iterator[ExtractResult]:
    """Yield one validated result per (location, date window)."""
    variables = source_cfg["hourly_variables"]
    locations = list(locations if locations is not None else source_cfg["locations"])
    for loc in locations:
        for w_start, w_end in date_windows(start, end, source_cfg["request_window_days"]):
            params = {
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "start_date": w_start.isoformat(),
                "end_date": w_end.isoformat(),
                "hourly": ",".join(variables),
                "timezone": source_cfg.get("timezone", "UTC"),
            }
            response = client.get_json(source_cfg["archive_url"], params)
            rows = validate_payload(response.payload, variables)

            expected = ((w_end - w_start).days + 1) * 24
            if rows != expected:
                log.warning(
                    "unexpected hourly row count",
                    extra={"source": SOURCE, "location": loc["name"], "rows": rows, "expected": expected},
                )
            result = ExtractResult(
                source=SOURCE,
                entity=loc["name"],
                window_start=w_start,
                window_end=w_end,
                request_url=source_cfg["archive_url"],
                request_params=params,
                retrieved_at=utc_now(),
                payload=response.payload,
                record_count=rows,
            )
            raw_store.save(result)
            log.info(
                "extracted window",
                extra={"source": SOURCE, "entity": loc["name"], "window": f"{w_start}..{w_end}", "rows": rows},
            )
            yield result
