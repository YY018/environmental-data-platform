"""Backfill pipeline: extract -> transform -> load, for every enabled source.

Run: python -m src.pipeline [--start YYYY-MM-DD] [--end YYYY-MM-DD]

Each source runs independently. If one source fails, the others still load and
the run is recorded as 'partial'. If every source fails, it is 'failed'.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from typing import Any, Callable, Iterable

from src.config import AppConfig, load_config
from src.database.connection import get_engine
from src.extract import open_meteo, openaq, usgs
from src.extract.common import ExtractResult, RawStore, ValidationError
from src.extract.http_client import HttpClient
from src.load import loader
from src.transform import air_quality, earthquakes, weather
from src.transform.common import nested_get

log = logging.getLogger(__name__)

SOURCE_NAMES = ("open_meteo", "openaq", "usgs")


def fetch_station_metadata(client: HttpClient, base_url: str, sensors: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Look up coordinates and provider for each OpenAQ station.

    The hourly endpoint returns no coordinates, but dim_location needs them.
    One request per station, deduplicated by location id.
    """
    seen: dict[int, dict[str, Any]] = {}
    for sensor in sensors:
        loc_id = sensor["location_id"]
        if loc_id in seen:
            continue
        payload = client.get_json(f"{base_url.rstrip('/')}/locations/{loc_id}").payload
        results = payload.get("results") if isinstance(payload, dict) else None
        if not results:
            raise ValidationError(f"OpenAQ location {loc_id} not found")
        loc = results[0]
        lat = nested_get(loc, "coordinates", "latitude")
        lon = nested_get(loc, "coordinates", "longitude")
        if lat is None or lon is None:
            raise ValidationError(f"OpenAQ location {loc_id} has no coordinates")
        seen[loc_id] = {
            "location_id": loc_id,
            "city": sensor["city"],
            "name": sensor["name"],
            "latitude": lat,
            "longitude": lon,
            "provider": nested_get(loc, "provider", "name"),
            "reference_monitor": bool(sensor["reference_monitor"]),
        }
    return list(seen.values())


def _handle_weather(engine, run_id: int, result: ExtractResult) -> int:
    rows, rejected = weather.to_rows(result.payload, result.entity, result.retrieved_at)
    watermark = max((r["observed_at"] for r in rows), default=None)
    return loader.load_page(engine, run_id, result, "weather", rows, rejected, watermark)


def _make_aq_handler(sensor_to_location: dict[int, int]) -> Callable[..., int]:
    def handle(engine, run_id: int, result: ExtractResult) -> int:
        sensor_id = int(result.entity)
        rows, rejected = air_quality.to_rows(
            result.payload, sensor_id, sensor_to_location[sensor_id], result.retrieved_at
        )
        watermark = max((r["period_end"] for r in rows), default=None)
        return loader.load_page(engine, run_id, result, "air_quality", rows, rejected, watermark)
    return handle


def _handle_earthquakes(engine, run_id: int, result: ExtractResult) -> int:
    rows, rejected = earthquakes.to_rows(result.payload, result.retrieved_at)
    watermark = max((r["source_updated_at"] for r in rows), default=None)
    return loader.load_page(engine, run_id, result, "earthquake", rows, rejected, watermark)


def _run_source(engine, run_id: int, name: str, results: Iterable[ExtractResult],
                handler: Callable[..., int]) -> int:
    loaded_total = 0
    for result in results:
        loaded_total += handler(engine, run_id, result)
    log.info("source complete", extra={"source": name, "rows_loaded": loaded_total})
    return loaded_total


def run_backfill(start: date, end: date, trigger: str = "local", cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    sources = cfg.sources
    http_cfg = cfg.settings["http"]
    raw = RawStore(cfg.path("raw_data"))
    engine = get_engine()

    run_id = loader.start_run(engine, "backfill", trigger)
    log.info("run started", extra={"run_id": run_id, "start": str(start), "end": str(end)})
    errors: dict[str, str] = {}
    enabled = [name for name in SOURCE_NAMES if sources[name].get("enabled")]

    try:
        with engine.begin() as conn:
            loader.seed_source_registry(conn, sources)

        stations: list[dict[str, Any]] = []
        if "openaq" in enabled:
            aq_client = openaq.build_client(http_cfg)
            stations = fetch_station_metadata(aq_client, sources["openaq"]["base_url"], sources["openaq"]["sensors"])
        with engine.begin() as conn:
            loader.seed_locations(conn, sources["open_meteo"]["locations"] if "open_meteo" in enabled else [], stations)
    except Exception as exc:
        loader.finish_run(engine, run_id, "failed", f"setup failed: {exc}")
        raise

    for name in enabled:
        try:
            client = HttpClient.from_settings(http_cfg)
            if name == "open_meteo":
                results = open_meteo.extract(client, raw, sources[name], start, end)
                handler: Callable[..., int] = _handle_weather
            elif name == "openaq":
                client = openaq.build_client(http_cfg)
                results = openaq.extract(client, raw, sources[name], start, end)
                mapping = {s["sensor_id"]: s["location_id"] for s in sources[name]["sensors"]}
                handler = _make_aq_handler(mapping)
            else:
                results = usgs.extract(client, raw, sources[name], start, end)
                handler = _handle_earthquakes
            _run_source(engine, run_id, name, results, handler)
        except Exception as exc:
            errors[name] = str(exc)
            log.error("source failed", extra={"source": name, "error": str(exc)})
            loader.log_event(engine, run_id, "ERROR", __name__, f"{name} failed", {"error": str(exc)})

    if not errors:
        status = "succeeded"
    elif len(errors) == len(enabled):
        status = "failed"
    else:
        status = "partial"
    message = "; ".join(f"{k}: {v}" for k, v in errors.items()) or None
    loader.finish_run(engine, run_id, status, message)
    log.info("run finished", extra={"run_id": run_id, "status": status})
    return {"run_id": run_id, "status": status, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    from src.monitoring.logger import configure_logging

    cfg = load_config()
    parser = argparse.ArgumentParser(description="Backfill environmental data into Postgres.")
    parser.add_argument("--start", default=cfg.settings["backfill"]["start_date"])
    parser.add_argument("--end", default=cfg.settings["backfill"]["end_date"])
    args = parser.parse_args(argv)

    configure_logging(cfg.settings["logging"]["level"], cfg.path("logs") / "pipeline.log")
    summary = run_backfill(date.fromisoformat(args.start), date.fromisoformat(args.end), cfg=cfg)
    print(f"Run {summary['run_id']}: {summary['status']}")
    for source, message in summary["errors"].items():
        print(f"  {source}: {message}")
    return 0 if summary["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
