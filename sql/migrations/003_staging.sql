-- 003: staging tables.
--
-- Why staging: pandas bulk-inserts a batch here quickly, then ONE set-based
-- INSERT ... SELECT ... ON CONFLICT merges it into analytics inside the same
-- transaction. Staging rows are deleted after the merge. Columns mirror the
-- analytics tables but without foreign keys or checks, so a bad row cannot
-- block the bulk load; validation happens in the merge and in the transform.

CREATE TABLE IF NOT EXISTS staging.weather_staging (
    batch_id               BIGINT       NOT NULL,
    location_key           TEXT         NOT NULL,
    observed_at            TIMESTAMPTZ  NOT NULL,
    temperature_c          NUMERIC(5,2),
    relative_humidity_pct  NUMERIC(5,2),
    precipitation_mm       NUMERIC(6,2),
    wind_speed_kmh         NUMERIC(6,2),
    weather_code           SMALLINT,
    grid_latitude          NUMERIC(9,6),
    grid_longitude         NUMERIC(9,6),
    grid_elevation_m       NUMERIC(7,2),
    source_retrieved_at    TIMESTAMPTZ  NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_weather_staging_batch ON staging.weather_staging (batch_id);

CREATE TABLE IF NOT EXISTS staging.air_quality_staging (
    batch_id               BIGINT       NOT NULL,
    sensor_id              BIGINT       NOT NULL,
    location_key           TEXT         NOT NULL,
    period_start           TIMESTAMPTZ  NOT NULL,
    period_end             TIMESTAMPTZ  NOT NULL,
    parameter              TEXT,
    units                  TEXT,
    value                  NUMERIC(10,3),
    min_value              NUMERIC(10,3),
    max_value              NUMERIC(10,3),
    observed_count         INTEGER,
    expected_count         INTEGER,
    percent_coverage       NUMERIC(6,2),
    has_flags              BOOLEAN,
    source_retrieved_at    TIMESTAMPTZ  NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_aq_staging_batch ON staging.air_quality_staging (batch_id);

CREATE TABLE IF NOT EXISTS staging.earthquake_staging (
    batch_id            BIGINT       NOT NULL,
    event_id            TEXT         NOT NULL,
    event_time          TIMESTAMPTZ  NOT NULL,
    source_updated_at   TIMESTAMPTZ  NOT NULL,
    magnitude           NUMERIC(4,2),
    magnitude_type      TEXT,
    place               TEXT,
    latitude            NUMERIC(9,6),
    longitude           NUMERIC(9,6),
    depth_km            NUMERIC(7,3),
    event_type          TEXT,
    review_status       TEXT,
    tsunami_flag        BOOLEAN,
    significance        INTEGER,
    felt_reports        INTEGER,
    alert_level         TEXT,
    network             TEXT,
    alternate_ids       TEXT[],
    detail_url          TEXT,
    source_retrieved_at TIMESTAMPTZ  NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_eq_staging_batch ON staging.earthquake_staging (batch_id);
