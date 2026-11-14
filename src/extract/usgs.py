"""USGS FDSN event extractor (global earthquakes, GeoJSON)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Iterator

from src.extract.common import ExtractResult, RawStore, ValidationError, date_windows, utc_now
from src.extract.http_client import HttpClient

log = logging.getLogger(__name__)
SOURCE = "usgs"


def validate_payload(payload: dict[str, Any]) -> int:
    if payload.get("type") != "FeatureCollection":
        raise ValidationError("Response is not a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValidationError("Response has no features list")
    declared = payload.get("metadata", {}).get("count")
    if declared is not None and declared != len(features):
        raise ValidationError(f"metadata.count={declared} but {len(features)} features returned")
    for i, feature in enumerate(features):
        if not feature.get("id"):
            raise ValidationError(f"Feature {i} has no id")
        coords = (feature.get("geometry") or {}).get("coordinates")
        if not isinstance(coords, list) or len(coords) < 2:
            raise ValidationError(f"Feature {feature['id']} has invalid coordinates")
    return len(features)


def _count(client: HttpClient, cfg: dict[str, Any], params: dict[str, Any]) -> int:
    response = client.get_json(cfg["count_url"], params)
    try:
        return int(response.payload["count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("Count endpoint returned no count") from exc


def _query_window(
    client: HttpClient,
    raw_store: RawStore,
    cfg: dict[str, Any],
    w_start: date,
    w_end: date,
    updated_after: datetime | None,
) -> Iterator[ExtractResult]:
    params: dict[str, Any] = {
        "format": "geojson",
        "starttime": f"{w_start.isoformat()}T00:00:00",
        # Next midnight; an event exactly at midnight may appear in two windows,
        # which the upsert on event id makes harmless.
        "endtime": f"{(w_end + timedelta(days=1)).isoformat()}T00:00:00",
        "minmagnitude": cfg["min_magnitude"],
        "orderby": "time-asc",
    }
    if updated_after is not None:
        params["updatedafter"] = updated_after.strftime("%Y-%m-%dT%H:%M:%S")

    count = _count(client, cfg, params)
    if count > cfg["max_results_per_query"]:
        if w_start == w_end:
            raise ValidationError(f"{count} events in a single day exceeds the query limit")
        mid = w_start + (w_end - w_start) // 2
        log.info("window too large, splitting", extra={"source": SOURCE, "count": count})
        yield from _query_window(client, raw_store, cfg, w_start, mid, updated_after)
        yield from _query_window(client, raw_store, cfg, mid + timedelta(days=1), w_end, updated_after)
        return

    response = client.get_json(cfg["query_url"], params)
    rows = validate_payload(response.payload)
    result = ExtractResult(
        source=SOURCE,
        entity="global",
        window_start=w_start,
        window_end=w_end,
        request_url=cfg["query_url"],
        request_params=params,
        retrieved_at=utc_now(),
        payload=response.payload,
        record_count=rows,
    )
    raw_store.save(result)
    log.info(
        "extracted window",
        extra={"source": SOURCE, "window": f"{w_start}..{w_end}", "rows": rows, "counted": count},
    )
    yield result


def extract(
    client: HttpClient,
    raw_store: RawStore,
    source_cfg: dict[str, Any],
    start: date,
    end: date,
    updated_after: datetime | None = None,
) -> Iterator[ExtractResult]:
    """Yield one validated result per date window.

    ``updated_after`` (UTC) restricts results to events created or revised
    after that instant. Incremental runs use it to capture event revisions.
    """
    for w_start, w_end in date_windows(start, end, source_cfg["request_window_days"]):
        yield from _query_window(client, raw_store, source_cfg, w_start, w_end, updated_after)
