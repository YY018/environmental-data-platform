"""OpenAQ v3 extractor (hourly sensor measurements, paginated)."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Iterable, Iterator

from src.config import get_secret
from src.extract.common import ExtractResult, RawStore, ValidationError, date_windows, utc_now
from src.extract.http_client import HttpClient

log = logging.getLogger(__name__)
SOURCE = "openaq"
MAX_PAGES = 100  # safety stop against an endless pagination loop


def build_client(http_settings: dict[str, Any]) -> HttpClient:
    """HTTP client with the API key header. The key lives only in memory."""
    return HttpClient.from_settings(http_settings, headers={"X-API-Key": get_secret("OPENAQ_API_KEY")})


def validate_payload(payload: dict[str, Any]) -> int:
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValidationError("Response has no results list")
    for i, row in enumerate(results):
        try:
            row["period"]["datetimeFrom"]["utc"]
            row["parameter"]["name"]
        except (KeyError, TypeError) as exc:
            raise ValidationError(f"Row {i} lacks period/parameter fields") from exc
        if "value" not in row:
            raise ValidationError(f"Row {i} has no value field")
    return len(results)


def extract(
    client: HttpClient,
    raw_store: RawStore,
    source_cfg: dict[str, Any],
    start: date,
    end: date,
    sensors: Iterable[dict[str, Any]] | None = None,
) -> Iterator[ExtractResult]:
    """Yield one validated result per (sensor, window, page).

    Pagination stops when a page returns fewer rows than ``limit``: the API's
    ``meta.found`` may be a string such as ">1000", so it cannot be trusted
    as a total.
    """
    limit = source_cfg["page_limit"]
    url_template = source_cfg["base_url"].rstrip("/") + "/sensors/{sensor_id}/hours"
    sensors = list(sensors if sensors is not None else source_cfg["sensors"])

    for sensor in sensors:
        url = url_template.format(sensor_id=sensor["sensor_id"])
        for w_start, w_end in date_windows(start, end, source_cfg["request_window_days"]):
            for page in range(1, MAX_PAGES + 1):
                params = {
                    # Explicit Z: without it OpenAQ assumes station-local time.
                    "datetime_from": f"{w_start.isoformat()}T00:00:00Z",
                    "datetime_to": f"{(w_end + timedelta(days=1)).isoformat()}T00:00:00Z",
                    "limit": limit,
                    "page": page,
                }
                response = client.get_json(url, params)
                rows = validate_payload(response.payload)
                result = ExtractResult(
                    source=SOURCE,
                    entity=str(sensor["sensor_id"]),
                    window_start=w_start,
                    window_end=w_end,
                    request_url=url,
                    request_params=params,
                    retrieved_at=utc_now(),
                    payload=response.payload,
                    record_count=rows,
                    page=page,
                )
                raw_store.save(result)
                log.info(
                    "extracted page",
                    extra={"source": SOURCE, "entity": sensor["sensor_id"], "window": f"{w_start}..{w_end}",
                           "page": page, "rows": rows},
                )
                yield result
                if rows < limit:
                    break
            else:
                raise ValidationError(
                    f"Sensor {sensor['sensor_id']} exceeded {MAX_PAGES} pages; check the window size"
                )
