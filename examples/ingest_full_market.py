"""Daily full-market NSE bhavcopy ingestion script.

Downloads the bhavcopy for the given session from Samco via Playwright,
parses every NSE EQ row (not just portfolio symbols), validates the data,
and upserts it into the Neon database.

This is the script the GitHub Actions workflow (and any local cron) calls.

Usage:
    poetry run python examples/ingest_full_market.py --session 2026-09-25
    poetry run python examples/ingest_full_market.py --session 2026-09-25 --headless
    poetry run python examples/ingest_full_market.py --session 2026-09-25 --dry-run

Exit codes:
    0  – succeeded (or dry-run completed)
    1  – skipped (weekend / known non-trading day; not an error)
    2  – failed (download error, validation error, DB error)
"""

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from financial_assistant.features.investment_brief.data_quality import (
    assess_quote_dates,
)
from financial_assistant.ingestion.bhavcopy import load_bhavcopy_zip_full
from financial_assistant.ingestion.samco_downloader import download_bhavcopy
from financial_assistant.storage.market_repository import save_all_quotes


IST = ZoneInfo("Asia/Kolkata")

# NSE is closed on weekends.  Public holidays are handled separately via
# the trading_calendar table (migration 004).  This script skips weekends
# automatically and logs a clean skip for holidays found in that table.
WEEKEND = {5, 6}  # Saturday=5, Sunday=6


def is_trading_day(session: date) -> bool:
    """Return False for weekends; check DB for public holidays."""
    if session.weekday() in WEEKEND:
        return False

    # Optional: query the trading_calendar table if it exists.
    try:
        from financial_assistant.storage.database import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM trading_calendar
                        WHERE trading_date = %s
                          AND is_trading_day = FALSE
                    )
                    """,
                    (session,),
                )
                is_holiday = cur.fetchone()[0]
                return not is_holiday
    except Exception:
        # Table may not exist yet (migration 004 not applied).
        # Fall through and let the download itself fail if it's a holiday.
        return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and ingest the full NSE bhavcopy into Neon."
    )
    parser.add_argument(
        "--session",
        type=date.fromisoformat,
        default=None,
        help=(
            "Trading session date (YYYY-MM-DD). "
            "Defaults to today in IST."
        ),
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Playwright browser in headless mode (required in CI).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and parse but do not write to the database.",
    )
    args = parser.parse_args()

    session = args.session or datetime.now(IST).date()

    print(
        f"[{datetime.now(timezone.utc).isoformat()}] "
        f"Starting full-market ingestion for {session}"
    )

    # --- guard: skip non-trading days ---
    if not is_trading_day(session):
        print(f"[SKIP] {session} is not a trading day — nothing to do.")
        return 1

    # --- guard: refuse future sessions ---
    if session > datetime.now(IST).date():
        print(f"[ERROR] Session {session} is in the future.", file=sys.stderr)
        return 2

    # --- download via Playwright ---
    print(f"Downloading bhavcopy for {session} ...")
    try:
        downloaded_file: Path = download_bhavcopy(
            target_session=session,
            headless=args.headless,
        )
    except Exception as exc:
        print(f"[ERROR] Download failed: {exc}", file=sys.stderr)
        return 2

    print(f"Downloaded: {downloaded_file}  ({downloaded_file.stat().st_size:,} bytes)")

    # --- parse all EQ rows ---
    print("Parsing all NSE EQ rows ...")
    try:
        if downloaded_file.suffix.lower() == ".zip":
            quotes = load_bhavcopy_zip_full(downloaded_file, session)
        else:
            from financial_assistant.ingestion.bhavcopy import load_bhavcopy_full
            quotes = load_bhavcopy_full(downloaded_file)
    except Exception as exc:
        print(f"[ERROR] Parsing failed: {exc}", file=sys.stderr)
        return 2

    print(f"Parsed {len(quotes):,} EQ quotes.")

    # --- date quality check ---
    quality = assess_quote_dates(quotes, session)
    print(f"Date quality: {json.dumps(quality)}")

    if quality["status"] != "matches_target":
        print(
            f"[ERROR] Snapshot rejected — quote dates do not match {session}.",
            file=sys.stderr,
        )
        return 2

    # --- dry-run exit ---
    if args.dry_run:
        print("[DRY-RUN] Skipping database write.")
        sample = quotes[:5]
        for q in sample:
            print(f"  {q.symbol}: close={q.close}  pct={q.pct_change}%")
        return 0

    # --- persist to Neon ---
    print(f"Writing {len(quotes):,} rows to Neon ...")
    try:
        run_id = save_all_quotes(
            quotes=quotes,
            source_file=downloaded_file,
            target_session=session,
        )
    except ValueError as exc:
        # Duplicate file or bad data — not a transient error.
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[ERROR] Database write failed: {exc}", file=sys.stderr)
        return 2

    print(
        f"[OK] Ingestion run {run_id} succeeded — "
        f"{len(quotes):,} quotes saved for {session}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
