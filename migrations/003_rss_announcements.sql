CREATE TABLE rss_feed_snapshots (
    snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_sha256 TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    entry_count INTEGER NOT NULL CHECK (entry_count >= 0),
    normalized_count INTEGER NOT NULL CHECK (normalized_count >= 0),
    coverage_status TEXT NOT NULL DEFAULT 'feed_snapshot_only',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE rss_announcements (
    announcement_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source TEXT NOT NULL,
    source_entry_id TEXT NOT NULL,
    symbol TEXT,
    company_name TEXT NOT NULL,
    subject TEXT,
    details TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    attachment_url TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    UNIQUE (source, source_entry_id)
);

CREATE INDEX rss_announcements_symbol_date_idx
    ON rss_announcements (symbol, published_at DESC);

CREATE TABLE rss_snapshot_entries (
    snapshot_id BIGINT NOT NULL
        REFERENCES rss_feed_snapshots(snapshot_id),
    announcement_id BIGINT NOT NULL
        REFERENCES rss_announcements(announcement_id),
    PRIMARY KEY (snapshot_id, announcement_id)
);