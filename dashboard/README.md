# Power BI dashboard

The report reads the reporting views in the `analytics` and `monitoring`
schemas (migration `004_reporting_views.sql`). It never reads the staging or
raw tables.

## Pages

| Page | Source view | Shows |
|---|---|---|
| Weather | `analytics.v_weather_daily` | Daily temperature, rainfall and wind by city |
| Air quality | `analytics.v_pm25_daily`, `analytics.v_air_quality_hourly` | PM2.5 trend by city and station |
| Earthquakes | `analytics.v_earthquakes` | Map and magnitude by day, for events of magnitude 2.5 and above |
| Pipeline health | `monitoring.v_pipeline_health` | Every load run: status, rows loaded and rejected, errors |

## Connect Power BI Desktop

1. Open **Power BI Desktop** → **Get data** → **PostgreSQL database**.
2. **Server:** the host from `DATABASE_URL` in `.env`, the part between `@` and `/`,
   written as `host:5432`. **Database:** the name after the final `/`, before `?`.
3. Leave **Advanced options** empty and pick the views in the navigator.
4. Choose **Database** authentication. The username and password are the ones in `DATABASE_URL`.
   Power BI asks for them once and stores them in the report, so save the `.pbix`
   somewhere private.
5. In the navigator, tick the views listed above. Choose **Load**.
6. Under **Transform data**, check that the date columns are typed as Date or Date/Time.

## Relationships

Load `analytics.dim_date` as well and mark it as the date table, so time
intelligence works. Power BI may create these relationships automatically; check
them in the model view and link each `reading_date` (or `event_date`) column to
`dim_date[date_value]`.

## Measures

The DAX in `measures.dax` covers the headline numbers. Add them under
**New measure** in the model.

## Refresh

Power BI reads the database on refresh. The pipeline loads new data each day at
06:30 UTC, so a daily refresh after 07:00 UTC shows the latest numbers. In
Power BI Service, set the schedule under **Dataset settings → Scheduled refresh**. Neon is reachable
over TLS from the internet, so Power BI Service can refresh directly without a
gateway.

## Read-only access

Power BI should not use the owner credentials. Create a read-only role in Neon
and use that in Power BI instead. This is a one-off SQL step, not part of the
pipeline.
