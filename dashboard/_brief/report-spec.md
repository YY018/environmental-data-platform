# MyReport: locked spec (approved 2026-11-15)

Source: pasted build request, plan confirmed by the user.
Target: `dashboard\MyReport.pbix` (or the PBIP project saved from it).
Data: reporting views from `sql/migrations/004_reporting_views.sql`. Columns and
measures were checked against `dashboard\measures.dax` and match.

## Global layout
- Clean, consistent layout on every page.
- Tile-style slicers across the top of each page.
- Each page has a title and a subtitle showing the data date range.

## Page 1: Weather
- Slicers: `v_weather_daily[city]`, `dim_date[date_value]`.
- KPI cards: `Avg Temperature (°C)`, `Total Rainfall (mm)`, `Max Wind (km/h)`, `Days With Rain`.
- Line chart: `avg_temperature_c` by `reading_date`, one line per `city`.
  Title: "Average daily temperature by city (°C)".
- Column chart: `total_precipitation_mm` by `reading_date`.
  Title: "Daily rainfall (mm)".

## Page 2: Air quality
- Slicers: `v_pm25_daily[city]`, `dim_date[date_value]`.
- KPI cards: `Avg PM2.5 (µg/m³)`, `Days Above WHO Guideline`,
  `Share Of Days Above Guideline` (percentage), `Stations Reporting`.
- Line chart: `avg_pm25` by `reading_date`, one line per `city`.
  Title: "Daily average PM2.5 by city (µg/m³)".
  Constant reference line at 15, labelled "WHO guideline (24 h)".
- Table from `v_air_quality_hourly`: `city`, `station`, `is_reference_monitor`,
  `pm25`, `period_start`. Sort `period_start` descending.
  Title: "Latest station readings".

## Page 3: Earthquakes
- Slider: `v_earthquakes[magnitude]`, 2.5 to maximum.
- Slicer: `dim_date[date_value]`.
- KPI cards: `Event Count`, `Strongest Event`, `Avg Depth (km)`, `Tsunami Flags`.
- Map from `v_earthquakes`: latitude, longitude, size by `magnitude`.
  Tooltip: `place`, `magnitude`, `event_time`, `depth_km`.
- Column chart: `Event Count` by `event_date`. Title: "Events per day".
- Table: `place`, `magnitude`, `event_time`, `depth_km`, `tsunami_flag`.
  Sort `magnitude` descending.

## Page 4: Pipeline health
- KPI cards: `Last Successful Load` (date and time), `Failed Runs (last 7 days)`,
  `Rows Rejected (last 7 days)`.
- Table from `v_pipeline_health`: `run_id`, `run_type`, `trigger`, `status`,
  `started_at`, `duration_minutes`, `rows_loaded`, `rows_rejected`, `error_message`.
  Status colours: failed = red, partial = amber, succeeded = green.

## Known issues to fix or confirm
- "Failed Runs (last 7 days)" counts `failed` and `partial`. The label says "failed". Decide: rename the label or change the measure.
- Earthquakes map title is hardcoded as "15 Aug to 14 Nov 2026" in BUILD_STEPS.md. Use the dynamic date range instead.

## Out of scope
- Publishing to Fabric.
- Changes to SQL views or measures, unless the known issues above are approved.
