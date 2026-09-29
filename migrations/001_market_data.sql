CREATE TABLE instruments (
    instrument_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exchange TEXT NOT NULL,
    isin TEXT NOT NULL,
    series TEXT NOT NULL,
    symbol TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (exchange, isin, series)
);

CREATE INDEX instruments_symbol_idx
    ON instruments (exchange, symbol);


CREATE TABLE ingestion_runs (
    ingestion_run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source TEXT NOT NULL,
    source_file TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    target_session DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'started'
        CHECK (status IN ('started', 'succeeded', 'failed')),
    row_count INTEGER NOT NULL DEFAULT 0
        CHECK (row_count >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_message TEXT
);


CREATE TABLE daily_quotes (
    instrument_id BIGINT NOT NULL
        REFERENCES instruments (instrument_id),
    trading_date DATE NOT NULL,
    source TEXT NOT NULL,

    open NUMERIC NOT NULL CHECK (open > 0),
    high NUMERIC NOT NULL CHECK (high > 0),
    low NUMERIC NOT NULL CHECK (low > 0),
    close NUMERIC NOT NULL CHECK (close > 0),
    prev_close NUMERIC NOT NULL CHECK (prev_close > 0),
    pct_change NUMERIC NOT NULL,
    volume BIGINT NOT NULL CHECK (volume >= 0),

    ingestion_run_id BIGINT NOT NULL
        REFERENCES ingestion_runs (ingestion_run_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (instrument_id, trading_date, source),

    CHECK (low <= high),
    CHECK (open BETWEEN low AND high),
    CHECK (close BETWEEN low AND high)
);

CREATE INDEX daily_quotes_date_idx
    ON daily_quotes (trading_date);