"""Daily Google News RSS ingestion for portfolio symbols.

Reads the confirmed portfolio for the supplied user, extracts the symbol
list, then fetches and stores Google News RSS entries for those symbols only.

Usage:
    poetry run python examples/ingest_news_rss.py --user-id demo_user
    poetry run python examples/ingest_news_rss.py --user-id demo_user --dry-run

Exit codes:
    0  – succeeded (or dry-run completed)
    2  – failed
"""

import argparse
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from financial_assistant.ingestion.google_news_rss import ingest_news_for_symbols
from financial_assistant.storage.portfolio_repository import get_confirmed_portfolio


IST = ZoneInfo("Asia/Kolkata")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Google News RSS for portfolio symbols and store in Neon."
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="User ID whose confirmed portfolio determines which symbols to fetch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse but do not write to the database.",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=20,
        help="Maximum news entries to fetch per symbol (default: 20).",
    )
    args = parser.parse_args()

    now_ist = datetime.now(IST)
    print(
        f"[{datetime.now(tz=ZoneInfo('UTC')).isoformat()}] "
        f"Starting news ingestion for user '{args.user_id}'"
    )

    # --- resolve portfolio symbols ---
    try:
        versions = get_confirmed_portfolio(
            user_id=args.user_id,
            trading_date=now_ist.date(),
        )
    except ValueError as exc:
        print(f"[ERROR] Could not load portfolio: {exc}", file=sys.stderr)
        return 2

    symbols = sorted({
        holding["symbol"]
        for version in versions
        for holding in version["holdings"]
    })

    if not symbols:
        print("[ERROR] No symbols found in confirmed portfolio.", file=sys.stderr)
        return 2

    print(f"Portfolio symbols ({len(symbols)}): {', '.join(symbols)}")

    # --- fetch and store ---
    try:
        report = ingest_news_for_symbols(
            symbols=symbols,
            max_entries_per_symbol=args.max_entries,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"[ERROR] Ingestion failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2))

    if args.dry_run:
        print("[DRY-RUN] No data written to database.")
        return 0

    errors = report["totals"]["errors"]
    if errors == len(symbols):
        print(
            f"[ERROR] All {errors} symbol fetches failed.",
            file=sys.stderr,
        )
        return 2

    if errors:
        print(
            f"[WARN] {errors}/{len(symbols)} symbols had fetch errors "
            f"— partial ingestion completed."
        )

    print(
        f"[OK] Saved {report['totals']['saved']} news entries "
        f"for {len(symbols)} symbols."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
