import json
from datetime import date, datetime, timezone

import pytest

from src.config import load_config
from src.extract import open_meteo, openaq, usgs
from src.extract.common import ValidationError, date_windows
from tests.conftest import load_fixture, make_response

CFG = load_config().sources


# ---------- date windows ----------

def test_date_windows_cover_range_without_gaps_or_overlap():
    windows = list(date_windows(date(2026, 8, 15), date(2026, 11, 14), 14))
    assert windows[0][0] == date(2026, 8, 15)
    assert windows[-1][1] == date(2026, 11, 14)
    for (_, prev_end), (next_start, _) in zip(windows, windows[1:]):
        assert (next_start - prev_end).days == 1
    assert sum((e - s).days + 1 for s, e in windows) == 92


def test_date_windows_rejects_reversed_range():
    with pytest.raises(ValueError):
        list(date_windows(date(2026, 2, 1), date(2026, 1, 1), 7))


# ---------- Open-Meteo ----------

def test_open_meteo_extracts_and_saves_raw(make_client, raw_store):
    client, session, _ = make_client([make_response(200, load_fixture("open_meteo_archive_london_2d.json"))])
    london = [CFG["open_meteo"]["locations"][0]]
    results = list(open_meteo.extract(client, raw_store, CFG["open_meteo"],
                                      date(2026, 11, 13), date(2026, 11, 14), london))
    assert len(results) == 1 and results[0].record_count == 48
    params = session.calls[0]["params"]
    assert params["start_date"] == "2026-11-13" and params["timezone"] == "UTC"
    saved = json.loads(results[0].raw_path.read_text(encoding="utf-8"))
    assert saved["metadata"]["record_count"] == 48
    assert saved["payload"]["hourly"]["time"][0] == "2026-11-13T00:00"


def test_open_meteo_api_error_body_is_rejected():
    with pytest.raises(ValidationError, match="out of allowed range"):
        open_meteo.validate_payload(load_fixture("open_meteo_error_end_date.json"), ["temperature_2m"])


def test_open_meteo_misaligned_arrays_rejected():
    payload = load_fixture("open_meteo_archive_london_2d.json")
    payload["hourly"]["precipitation"].pop()
    with pytest.raises(ValidationError, match="precipitation"):
        open_meteo.validate_payload(payload, CFG["open_meteo"]["hourly_variables"])


# ---------- OpenAQ ----------

def _page(n_rows: int) -> dict:
    row = load_fixture("openaq_sensor_1561901_hours_1d.json")["results"][0]
    return {"meta": {"found": ">1"}, "results": [row] * n_rows}


def test_openaq_paginates_until_short_page(make_client, raw_store):
    cfg = {**CFG["openaq"], "page_limit": 2}
    client, session, _ = make_client([make_response(200, _page(2)), make_response(200, _page(2)),
                                      make_response(200, _page(1))])
    results = list(openaq.extract(client, raw_store, cfg, date(2026, 11, 13), date(2026, 11, 13),
                                  [{"sensor_id": 1561901}]))
    assert [r.page for r in results] == [1, 2, 3]
    assert len({r.raw_path for r in results}) == 3  # each page kept separately
    first = session.calls[0]
    assert first["url"].endswith("/sensors/1561901/hours")
    assert first["params"]["datetime_from"] == "2026-11-13T00:00:00Z"
    assert first["params"]["datetime_to"] == "2026-11-14T00:00:00Z"


def test_openaq_raw_file_contains_no_api_key(make_client, raw_store, monkeypatch):
    client, _, _ = make_client([make_response(200, _page(1))])
    client.session.headers["X-API-Key"] = "secret-key-123"
    [result] = openaq.extract(client, raw_store, CFG["openaq"], date(2026, 11, 13), date(2026, 11, 13),
                              [{"sensor_id": 1}])
    assert "secret-key-123" not in result.raw_path.read_text(encoding="utf-8")


def test_openaq_fixture_is_valid():
    assert openaq.validate_payload(load_fixture("openaq_sensor_1561901_hours_1d.json")) > 0


def test_openaq_row_without_period_rejected():
    with pytest.raises(ValidationError):
        openaq.validate_payload({"results": [{"value": 1, "parameter": {"name": "pm25"}}]})


# ---------- USGS ----------

def test_usgs_counts_then_queries(make_client, raw_store):
    fixture = load_fixture("usgs_query_6h.json")
    client, session, _ = make_client([make_response(200, {"count": fixture["metadata"]["count"]}),
                                      make_response(200, fixture)])
    [result] = usgs.extract(client, raw_store, CFG["usgs"], date(2026, 11, 13), date(2026, 11, 13))
    assert result.record_count == len(fixture["features"])
    assert session.calls[0]["url"].endswith("/count")
    assert session.calls[1]["params"]["endtime"] == "2026-11-14T00:00:00"
    assert session.calls[1]["params"]["minmagnitude"] == 2.5


def test_usgs_splits_window_over_limit(make_client, raw_store):
    cfg = {**CFG["usgs"], "max_results_per_query": 10}
    empty = {"type": "FeatureCollection", "metadata": {"count": 0}, "features": []}
    client, session, _ = make_client([
        make_response(200, {"count": 25}),                                      # 2 days: too many
        make_response(200, {"count": 5}), make_response(200, empty),            # day 1
        make_response(200, {"count": 5}), make_response(200, empty),            # day 2
    ])
    results = list(usgs.extract(client, raw_store, cfg, date(2026, 11, 1), date(2026, 11, 2)))
    assert [(r.window_start.day, r.window_end.day) for r in results] == [(1, 1), (2, 2)]


def test_usgs_updated_after_is_sent(make_client, raw_store):
    empty = {"type": "FeatureCollection", "metadata": {"count": 0}, "features": []}
    client, session, _ = make_client([make_response(200, {"count": 0}), make_response(200, empty)])
    list(usgs.extract(client, raw_store, CFG["usgs"], date(2026, 11, 13), date(2026, 11, 13),
                      updated_after=datetime(2026, 11, 14, 6, 30, tzinfo=timezone.utc)))
    assert session.calls[1]["params"]["updatedafter"] == "2026-11-14T06:30:00"


def test_usgs_count_mismatch_rejected():
    payload = load_fixture("usgs_query_6h.json")
    payload["features"].pop()
    with pytest.raises(ValidationError, match="metadata.count"):
        usgs.validate_payload(payload)
