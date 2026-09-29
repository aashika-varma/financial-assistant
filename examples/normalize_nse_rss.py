import argparse
import json
from pathlib import Path

from financial_assistant.ingestion.announcement_rss import (
    COMPANY_NAMES,
    normalize_entry,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()

    saved = json.loads(args.file.read_text(encoding="utf-8"))
    report = saved["report"]

    if report.get("parse_warning"):
        raise ValueError("Resolve the feed parse warning first")

    normalized = []
    errors = []
    seen = set()

    for index, entry in enumerate(saved["entries"], start=1):
        try:
            record = normalize_entry(
                entry,
                retrieved_at=report["retrieved_at"],
            )
        except (ValueError, TypeError) as exc:
            errors.append({
                "entry_number": index,
                "company_name": entry.get("title"),
                "published_raw": entry.get("published"),
                "error": str(exc),
            })
            continue

        entry_id = record["source_entry_id"]
        if entry_id not in seen:
            record["source_file"] = args.file.name
            normalized.append(record)
            seen.add(entry_id)

    matched = [
        record for record in normalized
        if record["symbol"] is not None
    ]
    matched.sort(key=lambda record: record["published_at"])

    counts = {
        symbol: sum(
            record["symbol"] == symbol for record in matched
        )
        for symbol in COMPANY_NAMES
    }

    output = {
        "source_inspection": str(args.file),
        "feed_report": report,
        "normalized_count": len(normalized),
        "matched_count": len(matched),
        "counts_by_symbol": counts,
        "errors": errors,
        "coverage_status": "feed_snapshot_only",
        "announcements": normalized,
    }

    output_path = args.file.with_name(
        f"{args.file.stem}_normalized.json"
    )
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("MATCH COUNTS")
    print(json.dumps(counts, indent=2))

    print("\nMATCHED ANNOUNCEMENTS")
    print(json.dumps(matched, indent=2, ensure_ascii=False))

    print(f"\nNormalization errors: {len(errors)}")
    print(f"Saved: {output_path}")

    if errors:
        print(json.dumps(errors, indent=2, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()