-- Migration 004: NSE trading calendar
--
-- Stores known NSE public holidays and market closures so the ingestion
-- job can skip non-trading days without attempting a bhavcopy download.
--
-- Populate this table manually each year from the NSE holiday list:
-- https://www.nseindia.com/resources/exchange-communication-holidays
--
-- The script examples/ingest_full_market.py queries this table via
-- is_trading_day().  If the table does not exist the job falls through
-- and lets the download itself fail for a genuine holiday.

CREATE TABLE trading_calendar (
    trading_date   DATE    NOT NULL PRIMARY KEY,
    is_trading_day BOOLEAN NOT NULL DEFAULT TRUE,
    description    TEXT,                          -- e.g. "Diwali", "Republic Day"
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE trading_calendar IS
    'NSE market open/closed days.  Only rows where is_trading_day = FALSE '
    'are meaningful for the ingestion guard; trading days need not be listed.';

-- Seed with NSE holidays for FY 2026-27.
-- Source: NSE circular (update annually).
INSERT INTO trading_calendar (trading_date, is_trading_day, description) VALUES
    ('2026-01-26', FALSE, 'Republic Day'),
    ('2026-02-26', FALSE, 'Mahashivratri'),
    ('2026-03-20', FALSE, 'Holi'),
    ('2026-03-25', FALSE, 'Good Friday'),
    ('2026-04-02', FALSE, 'Ram Navami'),
    ('2026-04-14', FALSE, 'Dr. Ambedkar Jayanti / Mahavir Jayanti'),
    ('2026-05-01', FALSE, 'Maharashtra Day'),
    ('2026-06-08', FALSE, 'Bakri Id (Eid ul-Adha)'),
    ('2026-08-15', FALSE, 'Independence Day'),
    ('2026-08-27', FALSE, 'Ganesh Chaturthi'),
    ('2026-10-02', FALSE, 'Gandhi Jayanti / Dussehra'),
    ('2026-10-20', FALSE, 'Diwali Laxmi Puja (Muhurat Trading — special session)'),
    ('2026-10-21', FALSE, 'Diwali Balipratipada'),
    ('2026-11-04', FALSE, 'Gurunanak Jayanti'),
    ('2026-12-25', FALSE, 'Christmas')
ON CONFLICT (trading_date) DO NOTHING;
