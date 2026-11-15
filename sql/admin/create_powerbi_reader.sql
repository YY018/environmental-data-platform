-- Read-only login for Power BI. Run ONCE as the database owner, not from the pipeline.
--
-- Before running: replace CHOOSE_A_STRONG_PASSWORD with a password you generate.
-- Store it only in Power BI's data source credentials and a password manager.
-- Never commit it.
--
-- The role can read the reporting views and dim_date. It cannot write, and it
-- cannot read the raw or staging tables.

CREATE ROLE powerbi_reader LOGIN PASSWORD 'CHOOSE_A_STRONG_PASSWORD'
    CONNECTION LIMIT 5;

GRANT USAGE ON SCHEMA analytics, monitoring TO powerbi_reader;

GRANT SELECT ON
    analytics.v_weather_hourly,
    analytics.v_weather_daily,
    analytics.v_air_quality_hourly,
    analytics.v_pm25_daily,
    analytics.v_earthquakes,
    analytics.dim_date,
    monitoring.v_pipeline_health
TO powerbi_reader;

-- Views run with the owner's privileges by default, so the reader does not
-- need access to the base tables behind them.
