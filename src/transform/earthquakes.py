"""USGS GeoJSON payload -> staging.earthquake_staging rows (one dict per event)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.transform.common import from_epoch_ms


def _alternate_ids(raw: str | None, own_id: str) -> list[str] | None:
    # USGS encodes the list as ",us7000txy5,ci123," and includes the event itself.
    if not raw:
        return None
    ids = [part for part in raw.split(",") if part and part != own_id]
    return ids or None


def to_rows(payload: dict[str, Any], retrieved_at: datetime) -> tuple[list[dict[str, Any]], int]:
    """Return (rows, rejected). Events missing time, id or location are rejected."""
    rows: list[dict[str, Any]] = []
    rejected = 0
    for feature in payload["features"]:
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        event_id = feature.get("id")
        event_time = from_epoch_ms(props.get("time"))
        updated = from_epoch_ms(props.get("updated"))
        if not event_id or event_time is None or updated is None or len(coords) < 2:
            rejected += 1
            continue
        rows.append({
            "batch_id": None,  # filled in by the loader
            "event_id": event_id,
            "event_time": event_time,
            "source_updated_at": updated,
            "magnitude": props.get("mag"),
            "magnitude_type": props.get("magType"),
            "place": props.get("place"),
            "latitude": coords[1],
            "longitude": coords[0],
            "depth_km": coords[2] if len(coords) > 2 else None,
            "event_type": props.get("type"),
            "review_status": props.get("status"),
            "tsunami_flag": None if props.get("tsunami") is None else bool(props.get("tsunami")),
            "significance": props.get("sig"),
            "felt_reports": props.get("felt"),
            "alert_level": props.get("alert"),
            "network": props.get("net"),
            "alternate_ids": _alternate_ids(props.get("ids"), event_id),
            "detail_url": props.get("detail") or props.get("url"),
            "source_retrieved_at": retrieved_at,
        })
    return rows, rejected
