-- 002: analytics model (what Power BI reads).
--
-- Star-like design: three fact tables at their natural grain, sharing
-- dim_date; weather and air quality also share dim_location.
-- Earthquakes are global points, not fixed sites, so they keep their own
-- coordinates instead of pointing at dim_location.

-- Calendar dimension, one row per day. Pre-populated so facts can reference it.
CREATE TABLE IF NOT EXISTS analytics.dim_date (
    date_value     DATE     PRIMARY KEY,
    year           SMALLINT NOT NULL,
    quarter        SMALLINT NOT NULL,
    month          SMALLINT NOT NULL,
    month_name     TEXT     NOT NULL,
    day_of_month   SMALLINT NOT NULL,
    day_of_week    SMALLINT NOT NULL,                    -- ISO: 1 = Monday
    day_name       TEXT     NOT NULL,
    iso_week       SMALLINT NOT NULL,
    is_weekend     BOOLEAN  NOT NULL
);

INSERT INTO analytics.dim_date
SELECT d::date,
       EXTRACT(YEAR FROM d), EXTRACT(QUARTER FROM d), EXTRACT(MONTH FROM d),
       TO_CHAR(d, 'FMMonth'), EXTRACT(DAY FROM d), EXTRACT(ISODOW FROM d),
       TO_CHAR(d, 'FMDay'), EXTRACT(WEEK FROM d), EXTRACT(ISODOW FROM d) IN (6, 7)
FROM generate_series(DATE '2020-01-01', DATE '2030-12-31', INTERVAL '1 day') AS d
ON CONFLICT (date_value) DO NOTHING;

-- Places we measure: city points (weather) and air-quality stations.
CREATE TABLE IF NOT EXISTS analytics.dim_location (
    location_id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    location_key          TEXT        NOT NULL UNIQUE,   -- 'city:london', 'openaq:270693'
    location_type         TEXT        NOT NULL CHECK (location_type IN ('city', 'aq_station')),
    name                  TEXT        NOT NULL,
    city                  TEXT        NOT NULL,          -- links stations to their city
    country_code          CHAR(2)     NOT NULL DEFAULT 'GB',
    latitude              NUMERIC(9,6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude             NUMERIC(9,6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    provider              TEXT,
    is_reference_monitor  BOOLEAN,                        -- NULL for cities
    source_location_id    BIGINT,                         -- OpenAQ location id
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_dim_location_city ON analytics.dim_location (city);

-- Grain: one row per city per UTC hour.
CREATE TABLE IF NOT EXISTS analytics.weather_readings (
    location_id            INTEGER      NOT NULL REFERENCES analytics.dim_location (location_id),
    observed_at            TIMESTAMPTZ  NOT NULL,
    reading_date           DATE         NOT NULL REFERENCES analytics.dim_date (date_value),
    temperature_c          NUMERIC(5,2),
    relative_humidity_pct  NUMERIC(5,2) CHECK (relative_humidity_pct BETWEEN 0 AND 100),
    precipitation_mm       NUMERIC(6,2) CHECK (precipitation_mm >= 0),
    wind_speed_kmh         NUMERIC(6,2) CHECK (wind_speed_kmh >= 0),
    weather_code           SMALLINT,
    grid_latitude          NUMERIC(9,6) NOT NULL,         -- model grid point returned by API
    grid_longitude         NUMERIC(9,6) NOT NULL,
    grid_elevation_m       NUMERIC(7,2),
    source_retrieved_at    TIMESTAMPTZ  NOT NULL,
    batch_id               BIGINT       NOT NULL REFERENCES monitoring.ingestion_batches (batch_id),
    inserted_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (location_id, observed_at)
);
CREATE INDEX IF NOT EXISTS ix_weather_observed ON analytics.weather_readings (observed_at);

-- Grain: one row per sensor per UTC hour (period start).
CREATE TABLE IF NOT EXISTS analytics.air_quality_readings (
    sensor_id              BIGINT       NOT NULL,         -- OpenAQ sensor id
    period_start           TIMESTAMPTZ  NOT NULL,
    period_end             TIMESTAMPTZ  NOT NULL,
    location_id            INTEGER      NOT NULL REFERENCES analytics.dim_location (location_id),
    reading_date           DATE         NOT NULL REFERENCES analytics.dim_date (date_value),
    parameter              TEXT         NOT NULL,         -- 'pm25'
    units                  TEXT         NOT NULL,         -- 'µg/m³'
    value                  NUMERIC(10,3),
    min_value              NUMERIC(10,3),
    max_value              NUMERIC(10,3),
    observed_count         INTEGER,
    expected_count         INTEGER,
    percent_coverage       NUMERIC(6,2),
    has_flags              BOOLEAN      NOT NULL DEFAULT FALSE,
    source_retrieved_at    TIMESTAMPTZ  NOT NULL,
    batch_id               BIGINT       NOT NULL REFERENCES monitoring.ingestion_batches (batch_id),
    inserted_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (sensor_id, period_start),
    CHECK (period_end > period_start)
);
CREATE INDEX IF NOT EXISTS ix_aq_location_time ON analytics.air_quality_readings (location_id, period_start);

-- Grain: one row per USGS event id (latest revision wins).
CREATE TABLE IF NOT EXISTS analytics.earthquake_events (
    event_id            TEXT         PRIMARY KEY,         -- e.g. 'us7000txx9'
    event_time          TIMESTAMPTZ  NOT NULL,
    event_date          DATE         NOT NULL REFERENCES analytics.dim_date (date_value),
    source_updated_at   TIMESTAMPTZ  NOT NULL,            -- USGS 'updated'
    magnitude           NUMERIC(4,2) CHECK (magnitude BETWEEN -2 AND 10),
    magnitude_type      TEXT,
    place               TEXT,
    latitude            NUMERIC(9,6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude           NUMERIC(9,6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    depth_km            NUMERIC(7,3),
    event_type          TEXT,                             -- earthquake, quarry blast, ...
    review_status       TEXT,                             -- automatic | reviewed | deleted
    tsunami_flag        BOOLEAN,
    significance        INTEGER,
    felt_reports        INTEGER,
    alert_level         TEXT,
    network             TEXT,
    alternate_ids       TEXT[],
    detail_url          TEXT,
    source_retrieved_at TIMESTAMPTZ  NOT NULL,
    batch_id            BIGINT       NOT NULL REFERENCES monitoring.ingestion_batches (batch_id),
    inserted_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_eq_time ON analytics.earthquake_events (event_time);
CREATE INDEX IF NOT EXISTS ix_eq_magnitude ON analytics.earthquake_events (magnitude);
