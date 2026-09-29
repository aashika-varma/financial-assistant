CREATE TABLE portfolio_accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_reference TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (user_id, account_reference)
);

CREATE TABLE portfolio_versions (
    portfolio_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL
        REFERENCES portfolio_accounts (account_id),
    holdings_as_of DATE NOT NULL,
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'confirmed', 'rejected')),
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_verification TEXT NOT NULL DEFAULT 'not_performed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ,

    UNIQUE (account_id, source_sha256),

    CHECK (
        (status = 'confirmed' AND confirmed_at IS NOT NULL)
        OR
        (status <> 'confirmed' AND confirmed_at IS NULL)
    )
);

CREATE TABLE portfolio_version_holdings (
    portfolio_version_id BIGINT NOT NULL
        REFERENCES portfolio_versions (portfolio_version_id),
    instrument_id BIGINT NOT NULL
        REFERENCES instruments (instrument_id),
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    source_page INTEGER NOT NULL CHECK (source_page > 0),
    extracted_evidence TEXT NOT NULL,

    PRIMARY KEY (portfolio_version_id, instrument_id)
);

CREATE INDEX portfolio_versions_lookup_idx
    ON portfolio_versions (
        account_id,
        holdings_as_of DESC,
        confirmed_at DESC
    )
    WHERE status = 'confirmed';