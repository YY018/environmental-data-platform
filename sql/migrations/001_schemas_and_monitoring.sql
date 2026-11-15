-- 001: logical schemas and pipeline monitoring tables.
--
-- raw        : untouched API responses (JSONB) for audit and reprocessing
-- staging    : typed, flattened rows of one batch, merged into analytics then cleared
-- analytics  : clean, deduplicated tables that Power BI reads
-- monitoring : run history, per-window batches (resumability), checkpoints, logs

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS monitoring;

-- One row per data source; referenced by every batch and response.
CREATE TABLE IF NOT EXISTS monitoring.source_registry (
    source_id     TEXT PRIMARY KEY,                      -- 'open_meteo' | 'openaq' | 'usgs'
    display_name  TEXT        NOT NULL,
    base_url      TEXT        NOT NULL,
    auth_type     TEXT        NOT NULL CHECK (auth_type IN ('none', 'api_key')),
    enabled       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per pipeline execution (local, scheduled or manual).
CREATE TABLE IF NOT EXISTS monitoring.pipeline_runs (
    run_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_type        TEXT        NOT NULL CHECK (run_type IN ('backfill', 'incremental')),
    trigger         TEXT        NOT NULL CHECK (trigger IN ('local', 'schedule', 'manual')),
    status          TEXT        NOT NULL DEFAULT 'running'
                                CHECK (status IN ('running', 'succeeded', 'partial', 'failed')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    git_sha         TEXT,
    rows_extracted  INTEGER     NOT NULL DEFAULT 0,
    rows_loaded     INTEGER     NOT NULL DEFAULT 0,
    rows_rejected   INTEGER     NOT NULL DEFAULT 0,
    error_message   TEXT,
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_started ON monitoring.pipeline_runs (started_at DESC);

-- One row per (source, entity, date window) processed in a run.
-- Backfill resumability: a window with a 'succeeded' backfill batch is skipped.
CREATE TABLE IF NOT EXISTS monitoring.ingestion_batches (
    batch_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id            BIGINT      NOT NULL REFERENCES monitoring.pipeline_runs (run_id),
    source_id         TEXT        NOT NULL REFERENCES monitoring.source_registry (source_id),
    entity            TEXT        NOT NULL,              -- city name, sensor id or 'global'
    window_start      DATE        NOT NULL,
    window_end        DATE        NOT NULL,
    status            TEXT        NOT NULL DEFAULT 'running'
                                  CHECK (status IN ('running', 'succeeded', 'failed')),
    records_extracted INTEGER     NOT NULL DEFAULT 0,
    records_loaded    INTEGER     NOT NULL DEFAULT 0,
    records_rejected  INTEGER     NOT NULL DEFAULT 0,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ,
    error_message     TEXT,
    CHECK (window_end >= window_start)
);
CREATE INDEX IF NOT EXISTS ix_batches_lookup
    ON monitoring.ingestion_batches (source_id, entity, window_start, window_end, status);
CREATE INDEX IF NOT EXISTS ix_batches_run ON monitoring.ingestion_batches (run_id);

-- High-water mark per (source, entity) for incremental runs.
-- Updated in the same transaction as the data it describes.
CREATE TABLE IF NOT EXISTS monitoring.ingestion_checkpoints (
    source_id       TEXT        NOT NULL REFERENCES monitoring.source_registry (source_id),
    entity          TEXT        NOT NULL,
    high_watermark  TIMESTAMPTZ NOT NULL,                -- latest data time successfully loaded
    last_run_id     BIGINT      REFERENCES monitoring.pipeline_runs (run_id),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, entity)
);

-- Warnings and errors from runs, queryable from Power BI's health page.
CREATE TABLE IF NOT EXISTS monitoring.etl_logs (
    log_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id      BIGINT      REFERENCES monitoring.pipeline_runs (run_id),
    logged_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    level       TEXT        NOT NULL,
    logger      TEXT        NOT NULL,
    message     TEXT        NOT NULL,
    context     JSONB
);
CREATE INDEX IF NOT EXISTS ix_etl_logs_run ON monitoring.etl_logs (run_id, logged_at);

-- Raw API responses. On GitHub Actions the local data/raw folder disappears
-- after each run, so the database is the durable copy. Pruned by retention job.
CREATE TABLE IF NOT EXISTS raw.api_responses (
    response_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id        BIGINT      NOT NULL REFERENCES monitoring.ingestion_batches (batch_id),
    source_id       TEXT        NOT NULL REFERENCES monitoring.source_registry (source_id),
    entity          TEXT        NOT NULL,
    page            INTEGER     NOT NULL DEFAULT 1,
    request_url     TEXT        NOT NULL,
    request_params  JSONB       NOT NULL,                -- never contains credentials
    retrieved_at    TIMESTAMPTZ NOT NULL,
    record_count    INTEGER     NOT NULL,
    payload         JSONB       NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_api_responses_batch ON raw.api_responses (batch_id);
CREATE INDEX IF NOT EXISTS ix_api_responses_retrieved ON raw.api_responses (retrieved_at);
