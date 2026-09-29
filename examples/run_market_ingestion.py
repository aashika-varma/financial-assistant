import argparse
import json
from datetime import date, datetime, timezone

from financial_assistant.features.investment_brief.data_quality import (
    assess_quote_dates,
)
from financial_assistant.ingestion.bhavcopy import (
    load_bhavcopy,
    load_bhavcopy_zip,
)
from financial_assistant.ingestion.samco_downloader import (
    download_bhavcopy,
)


SYMBOLS = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "ITC", "LT"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and validate a market snapshot."
    )
    parser.add_argument(
        "--session",
        type=date.fromisoformat,
        required=True,
    )
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    downloaded_file = download_bhavcopy(
        target_session=args.session,
        headless=args.headless,
    )

    if downloaded_file.suffix.lower() == ".zip":
        quotes = load_bhavcopy_zip(
            downloaded_file,
            SYMBOLS,
            args.session,
        )
    elif downloaded_file.suffix.lower() == ".csv":
        quotes = load_bhavcopy(downloaded_file, SYMBOLS)
    else:
        raise ValueError(
            f"Unsupported download format: {downloaded_file.suffix}"
        )

    quality = assess_quote_dates(quotes, args.session)

    if quality["status"] != "matches_target":
        raise RuntimeError(
            f"Snapshot rejected: {json.dumps(quality)}"
        )

    snapshot = {
        "source": "samco_downloaded_nse_bhavcopy",
        "source_file": downloaded_file.name,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "requested_symbols": SYMBOLS,
        "date_quality": quality,
        "quotes": [
            quote.model_dump(mode="json")
            for quote in quotes
        ],
    }

    # Save beside the original download, only after validation succeeds.
    output_path = downloaded_file.parent / "validated_snapshot.json"
    temporary_path = output_path.with_suffix(".json.tmp")

    temporary_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_path.replace(output_path)

    print(f"Validated {len(quotes)} quotes for {args.session}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()