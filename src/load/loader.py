"""Load validated, transformed rows into the database.

One API page = one transaction:
  batch row -> raw response -> staging rows -> set-based merge into analytics
  -> staging cleared -> checkpoint and run counters updated.
Either everything for that page lands or nothing does, so a crash never leaves
half-loaded data. Merges are upserts keyed on the natural grain, so re-running
a window is harmless.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from src.extract.common import ExtractResult

# Each merge reads one batch from staging, keeps the newest copy of duplicate
# keys, and only overwrites stored rows whose source timestamp is not newer.

WEATHER_MERGE = f"""
INSERT INTO analytics.weather_readings (
    location_id, observed_at, reading_date, temperature_c, relative_humidity_pct,
    precipitation_mm, wind_speed_kmh, weather_code, grid_latitude, grid_longitude,
    grid_elevation_m, source_retrieved_at, batch_id)
SELECT DISTINCT ON (l.location_id, s.observed_at)
    l.location_id, s.observed_at, CAST(s.observed_at AT TIME ZONE 'UTC' AS DATE),
    s.temperature_c, s.relative_humidity_pct, s.precipitation_mm, s.wind_speed_kmh,
    s.weather_code, s.grid_latitude, s.grid_longitude, s.grid_elevation_m,
    s.source_retrieved_at, s.batch_id
FROM staging.weather_staging s
JOIN analytics.dim_location l ON l.location_key = s.location_key
WHERE s.batch_id = :batch_id
ORDER BY l.location_id, s.observed_at, s.source_retrieved_at DESC
ON CONFLICT (location_id, observed_at) DO UPDATE SET
    temperature_c = EXCLUDED.temperature_c,
    relative_humidity_pct = EXCLUDED.relative_humidity_pct,
    precipitation_mm = EXCLUDED.precipitation_mm,
    wind_speed_kmh = EXCLUDED.wind_speed_kmh,
    weather_code = EXCLUDED.weather_code,
    grid_latitude = EXCLUDED.grid_latitude,
    grid_longitude = EXCLUDED.grid_longitude,
    grid_elevation_m = EXCLUDED.grid_elevation_m,
    source_retrieved_at = EXCLUDED.source_retrieved_at,
    batch_id = EXCLUDED.batch_id,
    updated_at = now()
WHERE analytics.weather_readings.source_retrieved_at <= EXCLUDED.source_retrieved_at
"""

AQ_MERGE = """
INSERT INTO analytics.air_quality_readings (
    sensor_id, period_start, period_end, location_id, reading_date, parameter, units,
    value, min_value, max_value, observed_count, expected_count, percent_coverage,
    has_flags, source_retrieved_at, batch_id)
SELECT DISTINCT ON (s.sensor_id, s.period_start)
    s.sensor_id, s.period_start, s.period_end, l.location_id,
    CAST(s.period_start AT TIME ZONE 'UTC' AS DATE), s.parameter, s.units,
    s.value, s.min_value, s.max_value, s.observed_count, s.expected_count,
    s.percent_coverage, s.has_flags, s.source_retrieved_at, s.batch_id
FROM staging.air_quality_staging s
JOIN analytics.dim_location l ON l.location_key = s.location_key
WHERE s.batch_id = :batch_id
ORDER BY s.sensor_id, s.period_start, s.source_retrieved_at DESC
ON CONFLICT (sensor_id, period_start) DO UPDATE SET
    period_end = EXCLUDED.period_end,
    location_id = EXCLUDED.location_id,
    reading_date = EXCLUDED.reading_date,
    parameter = EXCLUDED.parameter,
    units = EXCLUDED.units,
    value = EXCLUDED.value,
    min_value = EXCLUDED.min_value,
    max_value = EXCLUDED.max_value,
    observed_count = EXCLUDED.observed_count,
    expected_count = EXCLUDED.expected_count,
    percent_coverage = EXCLUDED.percent_coverage,
    has_flags = EXCLUDED.has_flags,
    source_retrieved_at = EXCLUDED.source_retrieved_at,
    batch_id = EXCLUDED.batch_id,
    updated_at = now()
WHERE analytics.air_quality_readings.source_retrieved_at <= EXCLUDED.source_retrieved_at
"""

EQ_MERGE = """
INSERT INTO analytics.earthquake_events (
    event_id, event_time, event_date, source_updated_at, magnitude, magnitude_type, place,
    latitude, longitude, depth_km, event_type, review_status, tsunami_flag, significance,
    felt_reports, alert_level, network, alternate_ids, detail_url, source_retrieved_at, batch_id)
SELECT DISTINCT ON (s.event_id)
    s.event_id, s.event_time, CAST(s.event_time AT TIME ZONE 'UTC' AS DATE), s.source_updated_at,
    s.magnitude, s.magnitude_type, s.place, s.latitude, s.longitude, s.depth_km, s.event_type,
    s.review_status, s.tsunami_flag, s.significance, s.felt_reports, s.alert_level, s.network,
    s.alternate_ids, s.detail_url, s.source_retrieved_at, s.batch_id
FROM staging.earthquake_staging s
WHERE s.batch_id = :batch_id
ORDER BY s.event_id, s.source_updated_at DESC, s.source_retrieved_at DESC
ON CONFLICT (event_id) DO UPDATE SET
    event_time = EXCLUDED.event_time,
    event_date = EXCLUDED.event_date,
    source_updated_at = EXCLUDED.source_updated_at,
    magnitude = EXCLUDED.magnitude,
    magnitude_type = EXCLUDED.magnitude_type,
    place = EXCLUDED.place,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    depth_km = EXCLUDED.depth_km,
    event_type = EXCLUDED.event_type,
    review_status = EXCLUDED.review_status,
    tsunami_flag = EXCLUDED.tsunami_flag,
    significance = EXCLUDED.significance,
    felt_reports = EXCLUDED.felt_reports,
    alert_level = EXCLUDED.alert_level,
    network = EXCLUDED.network,
    alternate_ids = EXCLUDED.alternate_ids,
    detail_url = EXCLUDED.detail_url,
    source_retrieved_at = EXCLUDED.source_retrieved_at,
    batch_id = EXCLUDED.batch_id,
    updated_at = now()
WHERE analytics.earthquake_events.source_updated_at <= EXCLUDED.source_updated_at
"""

# Table name -> (staging table, merge statement). Whitelist: table names are
# never built from user or API input.
TARGETS: dict[str, tuple[str, str]] = {
    "weather": ("staging.weather_staging", WEATHER_MERGE),
    "air_quality": ("staging.air_quality_staging", AQ_MERGE),
    "earthquake": ("staging.earthquake_staging", EQ_MERGE),
}


# ---------- reference data ----------

def seed_source_registry(conn: Connection, sources: dict[str, Any]) -> None:
    rows = [
        {"source_id": "open_meteo", "display_name": "Open-Meteo Historical Weather",
         "base_url": sources["open_meteo"]["archive_url"], "auth_type": "none"},
        {"source_id": "openaq", "display_name": "OpenAQ",
         "base_url": sources["openaq"]["base_url"], "auth_type": "api_key"},
        {"source_id": "usgs", "display_name": "USGS Earthquake Catalog",
         "base_url": sources["usgs"]["query_url"], "auth_type": "none"},
    ]
    conn.execute(text("""
        INSERT INTO monitoring.source_registry (source_id, display_name, base_url, auth_type)
        VALUES (:source_id, :display_name, :base_url, :auth_type)
        ON CONFLICT (source_id) DO UPDATE SET
            display_name = EXCLUDED.display_name, base_url = EXCLUDED.base_url,
            auth_type = EXCLUDED.auth_type, updated_at = now()
    """), rows)


def seed_locations(conn: Connection, cities: list[dict[str, Any]], stations: list[dict[str, Any]]) -> None:
    """Upsert city and air-quality station dimension rows.

    ``stations`` items carry: location_id, city, name, latitude, longitude,
    provider, reference_monitor.
    """
    from src.transform.weather import location_key as city_key
    from src.transform.air_quality import location_key as station_key

    city_rows = [{
        "location_key": city_key(c["name"]), "location_type": "city", "name": c["name"],
        "city": c["name"], "latitude": c["latitude"], "longitude": c["longitude"],
        "provider": None, "is_reference_monitor": None, "source_location_id": None,
    } for c in cities]
    station_rows = [{
        "location_key": station_key(s["location_id"]), "location_type": "aq_station",
        "name": s["name"], "city": s["city"], "latitude": s["latitude"],
        "longitude": s["longitude"], "provider": s["provider"],
        "is_reference_monitor": s["reference_monitor"], "source_location_id": s["location_id"],
    } for s in stations]
    conn.execute(text("""
        INSERT INTO analytics.dim_location (
            location_key, location_type, name, city, latitude, longitude,
            provider, is_reference_monitor, source_location_id)
        VALUES (:location_key, :location_type, :name, :city, :latitude, :longitude,
                :provider, :is_reference_monitor, :source_location_id)
        ON CONFLICT (location_key) DO UPDATE SET
            name = EXCLUDED.name, city = EXCLUDED.city, latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude, provider = EXCLUDED.provider,
            is_reference_monitor = EXCLUDED.is_reference_monitor,
            source_location_id = EXCLUDED.source_location_id, updated_at = now()
    """), city_rows + station_rows)


# ---------- checkpoints ----------

def min_checkpoint(engine: Engine, source_id: str) -> datetime | None:
    """Oldest high-water mark across a source's entities.

    Using the minimum means no entity can be left with a gap: the oldest one
    sets where the next incremental run starts.
    """
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT MIN(high_watermark) FROM monitoring.ingestion_checkpoints
            WHERE source_id = :source
        """), {"source": source_id}).scalar()


# ---------- runs ----------

def start_run(engine: Engine, run_type: str, trigger: str) -> int:
    with engine.begin() as conn:
        return conn.execute(text("""
            INSERT INTO monitoring.pipeline_runs (run_type, trigger)
            VALUES (:run_type, :trigger) RETURNING run_id
        """), {"run_type": run_type, "trigger": trigger}).scalar_one()


def finish_run(engine: Engine, run_id: int, status: str, error_message: str | None) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE monitoring.pipeline_runs
            SET status = :status, finished_at = now(), error_message = :error
            WHERE run_id = :run_id
        """), {"status": status, "error": error_message, "run_id": run_id})


# ---------- one page ----------

def _get_or_create_batch(conn: Connection, run_id: int, result: ExtractResult) -> int:
    existing = conn.execute(text("""
        SELECT batch_id FROM monitoring.ingestion_batches
        WHERE run_id = :run_id AND source_id = :source AND entity = :entity
          AND window_start = :ws AND window_end = :we
    """), {"run_id": run_id, "source": result.source, "entity": result.entity,
           "ws": result.window_start, "we": result.window_end}).scalar()
    if existing is not None:
        return existing
    return conn.execute(text("""
        INSERT INTO monitoring.ingestion_batches
            (run_id, source_id, entity, window_start, window_end, status)
        VALUES (:run_id, :source, :entity, :ws, :we, 'running')
        RETURNING batch_id
    """), {"run_id": run_id, "source": result.source, "entity": result.entity,
           "ws": result.window_start, "we": result.window_end}).scalar_one()


def _insert_raw(conn: Connection, batch_id: int, result: ExtractResult) -> None:
    conn.execute(text("""
        INSERT INTO raw.api_responses
            (batch_id, source_id, entity, page, request_url, request_params,
             retrieved_at, record_count, payload)
        VALUES (:batch_id, :source, :entity, :page, :url, CAST(:params AS JSONB),
                :retrieved_at, :record_count, CAST(:payload AS JSONB))
    """), {
        "batch_id": batch_id, "source": result.source, "entity": result.entity,
        "page": result.page, "url": result.request_url,
        "params": json.dumps(result.request_params, default=str),
        "retrieved_at": result.retrieved_at, "record_count": result.record_count,
        "payload": json.dumps(result.payload, ensure_ascii=False),
    })


def _stage(conn: Connection, table: str, batch_id: int, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    for row in rows:
        row["batch_id"] = batch_id
    columns = list(rows[0].keys())
    placeholders = ", ".join(f":{c}" for c in columns)
    conn.execute(
        text(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"),
        rows,
    )


def load_page(
    engine: Engine,
    run_id: int,
    result: ExtractResult,
    target: str,
    rows: list[dict[str, Any]],
    rejected: int,
    watermark: datetime | None,
) -> int:
    """Load one page atomically. Returns the number of analytics rows written."""
    staging_table, merge_sql = TARGETS[target]
    with engine.begin() as conn:
        batch_id = _get_or_create_batch(conn, run_id, result)
        _insert_raw(conn, batch_id, result)
        _stage(conn, staging_table, batch_id, rows)
        loaded = conn.execute(text(merge_sql), {"batch_id": batch_id}).rowcount or 0
        conn.execute(text(f"DELETE FROM {staging_table} WHERE batch_id = :batch_id"), {"batch_id": batch_id})

        conn.execute(text("""
            UPDATE monitoring.ingestion_batches
            SET status = 'succeeded',
                records_extracted = records_extracted + :extracted,
                records_loaded = records_loaded + :loaded,
                records_rejected = records_rejected + :rejected,
                finished_at = now()
            WHERE batch_id = :batch_id
        """), {"extracted": result.record_count, "loaded": loaded, "rejected": rejected, "batch_id": batch_id})

        conn.execute(text("""
            UPDATE monitoring.pipeline_runs
            SET rows_extracted = rows_extracted + :extracted,
                rows_loaded = rows_loaded + :loaded,
                rows_rejected = rows_rejected + :rejected
            WHERE run_id = :run_id
        """), {"extracted": result.record_count, "loaded": loaded, "rejected": rejected, "run_id": run_id})

        if watermark is not None:
            conn.execute(text("""
                INSERT INTO monitoring.ingestion_checkpoints (source_id, entity, high_watermark, last_run_id)
                VALUES (:source, :entity, :wm, :run_id)
                ON CONFLICT (source_id, entity) DO UPDATE SET
                    high_watermark = GREATEST(monitoring.ingestion_checkpoints.high_watermark, EXCLUDED.high_watermark),
                    last_run_id = EXCLUDED.last_run_id,
                    updated_at = now()
            """), {"source": result.source, "entity": result.entity, "wm": watermark, "run_id": run_id})
    return loaded


def log_event(engine: Engine, run_id: int | None, level: str, logger: str, message: str,
              context: dict[str, Any] | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO monitoring.etl_logs (run_id, level, logger, message, context)
            VALUES (:run_id, :level, :logger, :message, CAST(:context AS JSONB))
        """), {"run_id": run_id, "level": level, "logger": logger, "message": message,
               "context": json.dumps(context or {}, default=str)})
