# Build steps for the four report pages

Do the setup in `README.md` first (connect to the views, check relationships).
Then build the pages in this order. Each visual names the view, the fields and
the measures from `measures.dax`.

## Page 1: Weather

1. Rename **Page 1** to `Weather` (double-click the tab).
2. **Slicer**: Insert → Slicer. Field: `v_weather_daily[city]`. Format → Slicer
   settings → Style: **Tile**. Put it across the top.
3. **Slicer**: Insert → Slicer. Field: `dim_date[date_value]`. Set it to
   **Between**. Put it next to the city slicer.
4. **KPI cards** (Insert → Card), one each:
   - `[Avg Temperature (°C)]`
   - `[Total Rainfall (mm)]`
   - `[Max Wind (km/h)]`
   - `[Days With Rain]`
5. **Line chart**: Insert → Line chart.
   - X-axis: `v_weather_daily[reading_date]`
   - Y-axis: `v_weather_daily[avg_temperature_c]`
   - Legend: `v_weather_daily[city]`
   - Title: "Average daily temperature by city (°C)"
6. **Column chart**: Insert → Clustered column chart.
   - X-axis: `v_weather_daily[reading_date]`
   - Y-axis: `v_weather_daily[total_precipitation_mm]`
   - Title: "Daily rainfall (mm)"

## Page 2: Air quality

1. Add a new page, rename it `Air quality`.
2. **Slicer**: `v_pm25_daily[city]`, style Tile, across the top.
3. **Slicer**: `dim_date[date_value]`, Between.
4. **KPI cards**:
   - `[Avg PM2.5 (µg/m³)]`
   - `[Days Above WHO Guideline]`
   - `[Share Of Days Above Guideline]` (format as percentage)
   - `[Stations Reporting]`
5. **Line chart**: X-axis `v_pm25_daily[reading_date]`, Y-axis
   `v_pm25_daily[avg_pm25]`, Legend `v_pm25_daily[city]`.
   Title: "Daily average PM2.5 by city (µg/m³)".
6. **Reference line** on that chart: Analytics pane (magnifier icon) → Add
   line → Value **15** → label "WHO guideline (24 h)".
7. **Table**: columns `v_air_quality_hourly[city]`, `[station]`,
   `[is_reference_monitor]`, `[pm25]`, `[period_start]`. Sort by `period_start`
   descending. Title: "Latest station readings".

## Page 3: Earthquakes

1. Add a new page, rename it `Earthquakes`.
2. **Slicer**: `v_earthquakes[magnitude]`, set to **Between** (the data starts
   at 2.5, so the slider runs from 2.5 to the maximum).
3. **Slicer**: `dim_date[date_value]`, Between.
4. **KPI cards**:
   - `[Event Count]`
   - `[Strongest Event]`
   - `[Avg Depth (km)]`
   - `[Tsunami Flags]`
5. **Map**: Insert → Map (or Azure Map).
   - Latitude `v_earthquakes[latitude]`, Longitude `v_earthquakes[longitude]`
   - Size: `v_earthquakes[magnitude]`
   - Tooltips: `place`, `magnitude`, `event_time`, `depth_km`
   - Title: "Earthquakes, 15 Aug to 14 Nov 2026"
6. **Column chart**: X-axis `v_earthquakes[event_date]`, Y-axis
   `Event Count`. Title: "Events per day".
7. **Table**: `place`, `magnitude`, `event_time`, `depth_km`, `tsunami_flag`.
   Sort by `magnitude` descending.

## Page 4: Pipeline health

1. Add a new page, rename it `Pipeline health`.
2. **KPI cards**:
   - `[Last Successful Load]` (format as date and time)
   - `[Failed Runs (last 7 days)]`
   - `[Rows Rejected (last 7 days)]`
3. **Table**: source `monitoring.v_pipeline_health`. Columns: `run_id`,
   `run_type`, `trigger`, `status`, `started_at`, `duration_minutes`,
   `rows_loaded`, `rows_rejected`, `error_message`.
   Turn on **conditional formatting** for `status`: red for `failed`, amber for
   `partial`, green for `succeeded`.

## Finish

- **Page order**: Weather, Air quality, Earthquakes, Pipeline health.
- **Title and subtitle** on each page with the data date range.
- **Save** the file as `dashboard\MyReport.pbix`.
- Check every visual shows data. If one is blank, the most common cause is a
  slicer filtering out all rows, so reset the slicers and try again.

When a page is done, send me a screenshot and I'll check it against this list.
