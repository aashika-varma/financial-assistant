import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from financial_assistant.features.investment_brief.data_quality import (
    assess_quote_dates,
)
from financial_assistant.ingestion.bhavcopy import (
    load_bhavcopy,
    load_bhavcopy_zip,
)


SYMBOLS = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "ITC", "LT"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load and validate an NSE bhavcopy CSV."
    )
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--session", type=date.fromisoformat, required=True)
    args = parser.parse_args()

    if args.file.suffix.lower() == ".zip":
        quotes = load_bhavcopy_zip(
            args.file,
            SYMBOLS,
            args.session,
        )
    elif args.file.suffix.lower() == ".csv":
        quotes = load_bhavcopy(args.file, SYMBOLS)
    else:
        raise ValueError("Expected a .csv or .zip file")

    quality = assess_quote_dates(quotes, args.session)

    snapshot = {
        "source": "samco_downloaded_nse_bhavcopy",
        "source_file": args.file.name,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "requested_symbols": SYMBOLS,
        "date_quality": quality,
        "quotes": [
            quote.model_dump(mode="json")
            for quote in quotes
        ],
    }

    print(json.dumps(snapshot, indent=2, ensure_ascii=False))

    if quality["status"] != "matches_target":
        raise SystemExit(
            "Snapshot rejected: quote dates do not match the target session."
        )


if __name__ == "__main__":
    main()