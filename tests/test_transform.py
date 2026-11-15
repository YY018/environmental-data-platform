"""Transform tests: saved API payloads -> staging row dicts. No database needed."""

from datetime import datetime, timezone

from src.transform import air_quality, earthquakes, weather
from src.transform.common import fix_mojibake, parse_utc
from tests.conftest import load_fixture

RETRIEVED = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


# ---------- common helpers ----------

def test_parse_utc_accepts_z_suffix_and_naive_strings():
    assert parse_utc("2026-11-13T00:00:00Z") == datetime(2026, 11, 13, tzinfo=timezone.utc)
    assert parse_utc("2026-11-13T00:00") == datetime(2026, 11, 13, tzinfo=timezone.utc)


def test_fix_mojibake_repairs_double_encoded_units_and_leaves_clean_text_alone():
    assert fix_mojibake("Âµg/mÂ³") == "µg/m³"
    assert fix_mojibake("µg/m³") == "µg/m³"
    assert fix_mojibake(None) is None


# ---------- Open-Meteo ----------

def test_weather_rows_one_per_hour_with_grid_metadata():
    payload = load_fixture("open_meteo_archive_london_2d.json")
    rows, rejected = weather.to_rows(payload, "London", RETRIEVED)

    assert rejected == 0
    assert len(rows) == len(payload["hourly"]["time"])
    first = rows[0]
    assert first["location_key"] == "city:london"
    assert first["observed_at"] == datetime(2026, 11, 13, 0, tzinfo=timezone.utc)
    assert first["temperature_c"] == 2.5
    assert first["relative_humidity_pct"] == 78
    assert first["weather_code"] == 0
    assert first["grid_latitude"] == payload["latitude"]
    assert first["grid_elevation_m"] == payload["elevation"]
    assert first["source_retrieved_at"] == RETRIEVED


def test_weather_rows_are_unique_per_hour():
    payload = load_fixture("open_meteo_archive_london_2d.json")
    rows, _ = weather.to_rows(payload, "London", RETRIEVED)
    stamps = [r["observed_at"] for r in rows]
    assert len(stamps) == len(set(stamps))


def test_weather_location_key_is_lowercase_city():
    assert weather.location_key("Belfast") == "city:belfast"


# ---------- OpenAQ ----------

def test_air_quality_rows_match_fixture_hours():
    payload = load_fixture("openaq_sensor_1561901_hours_1d.json")
    rows, rejected = air_quality.to_rows(payload, 1561901, 270693, RETRIEVED)

    assert rejected == 0
    assert len(rows) == len(payload["results"])
    first = rows[0]
    assert first["sensor_id"] == 1561901
    assert first["location_key"] == "openaq:270693"
    assert first["parameter"] == "pm25"
    assert first["units"] == "µg/m³"  # mojibake in the fixture is repaired
    assert first["value"] == 6.3
    assert first["period_start"] == datetime(2026, 11, 13, 0, tzinfo=timezone.utc)
    assert first["period_end"] == datetime(2026, 11, 13, 1, tzinfo=timezone.utc)
    assert first["has_flags"] is False


def test_air_quality_skips_non_pm25_parameters():
    payload = load_fixture("openaq_sensor_1561901_hours_1d.json")
    payload["results"][0]["parameter"]["name"] = "no2"
    rows, rejected = air_quality.to_rows(payload, 1561901, 270693, RETRIEVED)
    assert rejected == 0
    assert len(rows) == len(payload["results"]) - 1


def test_air_quality_rejects_rows_with_inverted_period():
    payload = load_fixture("openaq_sensor_1561901_hours_1d.json")
    payload["results"][0]["period"]["datetimeTo"]["utc"] = payload["results"][0]["period"]["datetimeFrom"]["utc"]
    rows, rejected = air_quality.to_rows(payload, 1561901, 270693, RETRIEVED)
    assert rejected == 1
    assert len(rows) == len(payload["results"]) - 1


# ---------- USGS ----------

def test_earthquake_rows_match_fixture_events():
    payload = load_fixture("usgs_query_6h.json")
    rows, rejected = earthquakes.to_rows(payload, RETRIEVED)

    assert rejected == 0
    assert len(rows) == payload["metadata"]["count"]
    first = next(r for r in rows if r["event_id"] == "us7000txy5")
    assert first["magnitude"] == 4.7
    assert first["longitude"] == 116.7507   # GeoJSON order is lon, lat, depth
    assert first["latitude"] == -8.262
    assert first["depth_km"] == 9.626
    assert first["event_time"] == datetime.fromtimestamp(1794545373.549, tz=timezone.utc)
    assert first["source_updated_at"] == datetime.fromtimestamp(1794548167.087, tz=timezone.utc)
    assert first["tsunami_flag"] is False
    assert "us7000txy5" not in (first["alternate_ids"] or [])


def test_earthquake_rejects_features_without_location():
    payload = load_fixture("usgs_query_6h.json")
    payload["features"][0]["geometry"]["coordinates"] = []
    rows, rejected = earthquakes.to_rows(payload, RETRIEVED)
    assert rejected == 1
    assert len(rows) == len(payload["features"]) - 1
