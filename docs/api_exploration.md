# Phase 2 – API Exploration Findings

Explored on **2026-11-15**. Every statement below is tagged:

- **[verified-live]**: observed in a real API response.
- **[verified-docs]**: stated in official documentation (URL given).
- **[inference]**: our engineering conclusion, not stated by the source.

Sample responses are kept in `tests/fixtures/` for offline tests.

---

## 1. Open-Meteo Historical Weather API

Endpoint: `GET https://archive-api.open-meteo.com/v1/archive`.
Docs: https://open-meteo.com/en/docs/historical-weather-api

| Topic | Finding |
|---|---|
| Authentication | None. |
| Rate limits | 600 calls/min, 5,000/hour, 10,000/day on the free non-commercial tier. A request covering more than 2 weeks or more than 10 variables counts as multiple calls. **[verified-docs]** (https://open-meteo.com/en/terms, /en/pricing) |
| Latest date | `end_date=2026-11-15` returned HTTP 400: *"Parameter 'end_date' is out of allowed range from 1940-01-01 to 2026-11-14"*. At that moment it was 2026-11-14 ~23:00 **UTC** (04:30 on 15 Nov on the development laptop, UTC+5:30), so the archive accepts dates up to the **current UTC date**. Values for the current day are model output, not final reanalysis. **[verified-live]** |
| Data sources | The default "Best match" combines IFS HRES (no delay) with ERA5 and ERA5-Land (5-day delay). **[verified-docs]** |
| Revisions | The most recent ~5 days probably come from IFS and are replaced once ERA5 arrives, so incremental runs re-fetch a 7-day overlap. **[inference]** |
| Timestamps | `"2026-11-01T00:00"`, with no offset suffix. The offset is given separately as `utc_offset_seconds` (0 when `timezone=UTC`). The transform must attach UTC explicitly. **[verified-live]** |
| Coordinates | Snapped to the model grid: London was requested at (51.5074, -0.1278) and returned at (51.4938, -0.1630), elevation 16 m. Store both. **[verified-live]** |
| Units | Given in `hourly_units`: °C, %, mm, km/h, wmo code. **[verified-live]** |
| Volume | 92 days × 24 h × 10 cities = **22,080 rows** for 2026-08-15 to 2026-11-14. **[verified-live]** (shape: 24 rows per day per city) |
| Requests | 14-day windows give 7 requests per city, 70 in total, well within limits. |

## 2. OpenAQ API v3

Base URL: `https://api.openaq.org/v3`. Docs: https://docs.openaq.org/

| Topic | Finding |
|---|---|
| Authentication | `X-API-Key` header. A key of 64 characters was accepted. **[verified-live]** |
| Rate limits | 60/min and 2,000/hour per key. Exceeding them returns HTTP 429. Headers `X-Ratelimit-Limit`, `-Used`, `-Remaining`, `-Reset` are returned. **[verified-docs + live]** |
| Pagination | `limit` defaults to 100, maximum 1,000; pages are selected with `page`. `meta.found` can be a string such as `">3"` rather than a number, so loop until a page returns fewer than `limit` rows. **[verified-docs + live]** |
| Hourly endpoint | `GET /v3/sensors/{id}/hours?datetime_from=...&datetime_to=...`. Higher-frequency readings are averaged to the hour. **[verified-docs]** |
| Timezone pitfall | A timestamp without a timezone is interpreted as the station's local time, so always send `...Z`. **[verified-docs]** |
| Time convention | Each row has `period.datetimeFrom.utc` and `period.datetimeTo.utc`. We key rows on `datetimeFrom` (the period start). **[verified-live]** |
| Record fields | `value`, `parameter{id,name,units}`, `period{...}`, `summary{min..max,avg,sd}`, `coverage{expectedCount, observedCount, percentComplete, ...}`, `flagInfo.hasFlags`. **[verified-live]** |
| Parameters | pm25 = id 2 (µg/m³), pm10 = id 1. NO₂ and O₃ appear under several ids with different units, which would need unit handling if added later. **[verified-live]** |
| Latency | The latest hourly readings were for 21:00 UTC when checked at ~23:10 UTC, a lag of about 2 hours. Not documented. **[verified-live]** |

### Station coverage (2026-08-15 to 2026-11-14, 2,208 expected hours)

- 533 UK locations report PM2.5; 176 were active across the whole period. **[verified-live]**
- **A location being active does not mean its sensor is.** The Marylebone Road reference monitor had 4 of 2,208 hours. **[verified-live]**
- Outside London, every nearby station is an **AirGradient low-cost sensor** (`isMonitor=false`). Values are indicative, not of regulatory grade. **[verified-live]**
- **Cardiff has no active station.** The nearest is 42 km away in Bristol. This is recorded as a gap; we do not assign Bristol's data to Cardiff.
- 12 sensors were selected (see `config/sources.yaml`), with coverage between 92.4% and 99.7%. They contain **25,941 hourly rows** over the period. **[verified-live]**
- Rejected: Regent Street (stopped 28 Oct), Levenshulme (61%), Waterloo second sensor (no data), Marylebone (0.2%).

## 3. USGS FDSN Event Web Service

Endpoint: `GET https://earthquake.usgs.gov/fdsnws/event/1/query`, also `/count`.
Docs: https://earthquake.usgs.gov/fdsnws/event/1/

| Topic | Finding |
|---|---|
| Authentication | None. |
| Limits | At most 20,000 results per query; larger requests return HTTP 400. **[verified-docs]** |
| Times | ISO 8601; UTC unless a timezone is given. **[verified-docs]** |
| Volume | `/count` for 2026-08-15 to 2026-11-15 with M ≥ 2.5 returned **7,222 events**. **[verified-live]** |
| Identifier | `feature.id` (e.g. `us7000txx9`). `properties.ids` lists alternative IDs when several networks report the same event. **[verified-live]** |
| Geometry | `[longitude, latitude, depth_km]`, longitude first. **[verified-live]** |
| Timestamps | `properties.time` and `properties.updated` are epoch **milliseconds** in UTC. **[verified-live]** |
| Revisions | `status` is `automatic` or `reviewed`, and `updated` changes when an event is revised. `updatedafter` limits results to events updated after a given time. **[verified-docs + live]** |
| Guidance | The docs recommend real-time GeoJSON feeds for automated applications where possible. Our incremental design uses `query` with `updatedafter`, which the API supports, and keeps requests infrequent. **[verified-docs]** |

## 4. Decisions taken

1. **The backfill ends on 2026-11-14** (UTC). Open-Meteo rejects future UTC dates. Incremental ETL continues from there, and its overlap windows replace the provisional values for the latest days.
2. **Pair weather and air quality by city.** The 9 cities with sensors are matched; Cardiff has weather data only.
3. **Record the sensor type** (`reference_monitor`) so the dashboard can distinguish reference-grade and low-cost data.
4. **Overlap windows:** Open-Meteo 7 days, OpenAQ 48 hours, USGS 24 hours on `updatedafter`. Combined with upserts, this keeps re-runs free of duplicates.
5. **Every timestamp is stored as `TIMESTAMPTZ` in UTC.**
6. **The pipeline never uses the laptop's local clock.** The laptop runs at UTC+5:30, so 'today' differs from UTC for 5.5 hours a day.
