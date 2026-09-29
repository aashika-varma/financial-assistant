"""One-time historical bhavcopy backfill from NSE archives.

Downloads the full-market bhavcopy ZIP for every trading day in the past
N days directly from the NSE public archive — no Playwright required.
Skips dates already successfully ingested (idempotent: safe to re-run).

NSE archive URL pattern:
  https://nsearchives.nseindia.com/content/historical/EQUITIES/
      {YYYY}/{MON}/cm{DD}{MON}{YYYY}bhav.csv.zip

  Example: cm25SEP2026bhav.csv.zip

Usage:
    poetry run python examples/backfill_bhavcopy.py
    poetry run python examples/backfill_bhavcopy.py --days 365
    poetry run python examples/backfill_bhavcopy.py --start 2025-09-01 --end 2026-09-28
    poetry run python examples/backfill_bhavcopy.py --dry-run

Exit codes:
    0  – completed (partial success is also 0 — check the summary)
    2  – fatal setup error (bad args, no DB connection)
"""

import argparse
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

from financial_assistant.ingestion.bhavcopy import load_bhavcopy_zip_full
from financial_assistant.storage.market_repository import SOURCE, save_all_quotes
from financial_assistant.storage.database import get_connection

IST = ZoneInfo("Asia/Kolkata")
WEEKEND = {5, 6}  # Saturday=5, Sunday=6

# NSE archive base — public, no auth required.
_ARCHIVE_BASE = (
    "https://nsearchives.nseindia.com/content/historical/EQUITIES"
)
# Polite delay between requests so we don't hammer NSE servers.
_DELAY_SECONDS = 1.5

DOWNLOAD_DIR = Path("data/downloads/backfill")


def _archive_url(session: date) -> str:
    mon = session.strftime("%b").upper()   # SEP
    day = session.strftime("%d")            # 25
    year = session.strftime("%Y")           # 2026
    filename = f"cm{day}{mon}{year}bhav.csv.zip"
    return f"{_ARCHIVE_BASE}/{year}/{mon}/{filename}", filename


def _already_ingested(session: date) -> bool:
    """Return True if a successful ingestion run exists for this date."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM ingestion_runs
                    WHERE target_session = %s
                      AND source = %s
                      AND status = 'succeeded'
                    LIMIT 1
                    """,
                    (session, SOURCE),
                )
                return cur.fetchone() is not None
    except Exception:
        return False


def _is_known_holiday(session: date) -> bool:
    """Check trading_calendar table if available."""
    try:
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
                return cur.fetchone()[0]
    except Exception:
        return False


def _download(url: str, dest: Path) -> Path:
    """Download url to dest, return dest path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; financial-assistant/1.0; "
                "historical data backfill)"
            ),
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        dest.write_bytes(response.read())
    return dest


def _trading_days(start: date, end: date) -> list[date]:
    """All weekdays in [start, end] inclusive."""
    days = []
    current = start
    while current <= end:
        if current.weekday() not in WEEKEND:
            days.append(current)
        current += timedelta(days=1)
    return days


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill NSE bhavcopy from NSE public archives."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--days",
        type=int,
        default=365,
        help="Number of calendar days to look back from today IST (default: 365).",
    )
    group.add_argument(
        "--start",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Start date (inclusive). Use with --end.",
    )
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="End date (inclusive, default: yesterday IST). Use with --start.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and parse but do not write to the database.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=_DELAY_SECONDS,
        help=f"Seconds to wait between requests (default: {_DELAY_SECONDS}).",
    )
    args = parser.parse_args()

    today_ist = datetime.now(IST).date()
    yesterday_ist = today_ist - timedelta(days=1)

    if args.start:
        start = args.start
        end = args.end or yesterday_ist
        if start > end:
            print("[ERROR] --start must be before --end.", file=sys.stderr)
            return 2
    else:
        end = args.end or yesterday_ist
        start = end - timedelta(days=args.days - 1)

    if end >= today_ist:
        print(
            f"[WARN] end date {end} is today or future — "
            f"capping at {yesterday_ist}."
        )
        end = yesterday_ist

    candidates = _trading_days(start, end)
    print(
        f"[{datetime.now(timezone.utc).isoformat()}] "
        f"Backfill: {start} → {end}  |  {len(candidates)} weekdays to check"
    )

    results = {
        "skipped_already_ingested": [],
        "skipped_holiday": [],
        "skipped_404": [],
        "succeeded": [],
        "failed": [],
    }

    for i, session in enumerate(candidates):
        prefix = f"[{i+1}/{len(candidates)}] {session}"

        # Skip known holidays first (cheap DB check).
        if _is_known_holiday(session):
            print(f"{prefix}  SKIP  known holiday")
            results["skipped_holiday"].append(session)
            continue

        # Skip already-ingested sessions.
        if _already_ingested(session):
            print(f"{prefix}  SKIP  already ingested")
            results["skipped_already_ingested"].append(session)
            continue

        url, filename = _archive_url(session)
        dest = DOWNLOAD_DIR / filename

        # Download.
        try:
            _download(url, dest)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                print(f"{prefix}  SKIP  404 (holiday or no data)")
                results["skipped_404"].append(session)
                if i < len(candidates) - 1:
                    time.sleep(args.delay)
                continue
            print(f"{prefix}  FAIL  HTTP {exc.code}: {exc.reason}", file=sys.stderr)
            results["failed"].append((session, f"HTTP {exc.code}"))
            if i < len(candidates) - 1:
                time.sleep(args.delay)
            continue
        except Exception as exc:
            print(f"{prefix}  FAIL  download error: {exc}", file=sys.stderr)
            results["failed"].append((session, str(exc)))
            if i < len(candidates) - 1:
                time.sleep(args.delay)
            continue

        size_kb = dest.stat().st_size // 1024

        # Parse.
        try:
            quotes = load_bhavcopy_zip_full(dest, session)
        except Exception as exc:
            print(f"{prefix}  FAIL  parse error: {exc}", file=sys.stderr)
            results["failed"].append((session, f"parse: {exc}"))
            if i < len(candidates) - 1:
                time.sleep(args.delay)
            continue

        if args.dry_run:
            print(
                f"{prefix}  DRY-RUN  {len(quotes):,} quotes  "
                f"({size_kb:,} KB)  (not written)"
            )
            results["succeeded"].append(session)
            if i < len(candidates) - 1:
                time.sleep(args.delay)
            continue

        # Save.
        try:
            run_id = save_all_quotes(
                quotes=quotes,
                source_file=dest,
                target_session=session,
            )
            print(
                f"{prefix}  OK  run={run_id}  "
                f"{len(quotes):,} quotes  ({size_kb:,} KB)"
            )
            results["succeeded"].append(session)
        except ValueError as exc:
            # Duplicate file hash — treat as already ingested.
            print(f"{prefix}  SKIP  {exc}")
            results["skipped_already_ingested"].append(session)
        except Exception as exc:
            print(f"{prefix}  FAIL  db error: {exc}", file=sys.stderr)
            results["failed"].append((session, f"db: {exc}"))

        if i < len(candidates) - 1:
            time.sleep(args.delay)

    # Summary.
    print("\n── Backfill summary ──────────────────────────────────────")
    print(f"  Succeeded:               {len(results['succeeded'])}")
    print(f"  Already ingested (skip): {len(results['skipped_already_ingested'])}")
    print(f"  Holiday / no data:       {len(results['skipped_holiday']) + len(results['skipped_404'])}")
    if results["failed"]:
        print(f"  Failed:                  {len(results['failed'])}")
        for session, reason in results["failed"]:
            print(f"    {session}: {reason}")
    else:
        print(f"  Failed:                  0")
    print("──────────────────────────────────────────────────────────")

    return 0


if __name__ == "__main__":
    sys.exit(main())
