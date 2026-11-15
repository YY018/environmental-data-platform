-- 004: reporting views for Power BI.
--
-- Power BI reads these instead of the raw analytics tables: plain column names,
-- location names already joined, and daily roll-ups so the report stays fast.
-- Views hold no data, so they cost nothing to keep and can be changed later
-- by adding a new migration.

-- Hourly weather with the city name.
CREATE OR REPLACE VIEW analytics.v_weather_hourly AS
SELECT l.city,
       w.observed_at,
       w.reading_date,
       w.temperature_c,
       w.relative_humidity_pct,
       w.precipitation_mm,
       w.wind_speed_kmh,
       w.weather_code
FROM analytics.weather_readings w
JOIN analytics.dim_location l ON l.location_id = w.location_id;

-- Daily weather per city: the main chart for trends and comparisons.
CREATE OR REPLACE VIEW analytics.v_weather_daily AS
SELECT l.city,
       w.reading_date,
       ROUND(AVG(w.temperature_c), 1)          AS avg_temperature_c,
       MIN(w.temperature_c)                    AS min_temperature_c,
       MAX(w.temperature_c)                    AS max_temperature_c,
       ROUND(AVG(w.relative_humidity_pct), 1)  AS avg_humidity_pct,
       ROUND(SUM(w.precipitation_mm), 1)       AS total_precipitation_mm,
       ROUND(AVG(w.wind_speed_kmh), 1)         AS avg_wind_speed_kmh,
       MAX(w.wind_speed_kmh)                   AS max_wind_speed_kmh,
       COUNT(*)                                AS hours_observed
FROM analytics.weather_readings w
JOIN analytics.dim_location l ON l.location_id = w.location_id
GROUP BY l.city, w.reading_date;

-- Hourly PM2.5 per station.
CREATE OR REPLACE VIEW analytics.v_air_quality_hourly AS
SELECT l.city,
       l.name                  AS station,
       l.is_reference_monitor,
       a.sensor_id,
       a.period_start,
       a.reading_date,
       a.value                 AS pm25,
       a.min_value,
       a.max_value,
       a.percent_coverage,
       a.has_flags,
       a.units
FROM analytics.air_quality_readings a
JOIN analytics.dim_location l ON l.location_id = a.location_id;

-- Daily PM2.5 per city, averaged across its stations.
CREATE OR REPLACE VIEW analytics.v_pm25_daily AS
SELECT l.city,
       a.reading_date,
       ROUND(AVG(a.value), 2)     AS avg_pm25,
       ROUND(MAX(a.value), 2)     AS max_pm25,
       COUNT(DISTINCT a.sensor_id) AS stations_reporting
FROM analytics.air_quality_readings a
JOIN analytics.dim_location l ON l.location_id = a.location_id
GROUP BY l.city, a.reading_date;

-- Earthquakes, one row per event at its latest revision.
CREATE OR REPLACE VIEW analytics.v_earthquakes AS
SELECT event_id,
       event_time,
       event_date,
       magnitude,
       magnitude_type,
       place,
       latitude,
       longitude,
       depth_km,
       significance,
       felt_reports,
       tsunami_flag,
       review_status,
       event_type
FROM analytics.earthquake_events;

-- Pipeline health for a monitoring page: every run, newest first.
CREATE OR REPLACE VIEW monitoring.v_pipeline_health AS
SELECT run_id,
       run_type,
       trigger,
       status,
       started_at,
       finished_at,
       ROUND(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60, 1) AS duration_minutes,
       rows_extracted,
       rows_loaded,
       rows_rejected,
       error_message
FROM monitoring.pipeline_runs
ORDER BY started_at DESC;
