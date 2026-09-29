import json
from datetime import date, datetime, timezone
from pathlib import Path

from financial_assistant.ingestion.announcements import load_announcements
from financial_assistant.ingestion.announcement_downloads import (
    download_announcement,
)


def main() -> None:
    announcements = load_announcements(
        path=Path(
            "data/announcements/CF-AN-equities-TCS-29-Sep-2026.csv"
        ),
        symbols=["TCS"],
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 25),
    )

    results = []

    for announcement in announcements:
        result = download_announcement(
            announcement,
            output_dir=Path("data/announcements/pdfs"),
        )
        results.append(result)

        print(
            f"{result['published_at']} | "
            f"{result['subject']} | "
            f"{result['document_status']}"
        )

        if result.get("download_error"):
            print(f"  {result['download_error']}")

    manifest = {
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "symbols": ["TCS"],
        "start_date": "2026-09-21",
        "end_date": "2026-09-25",
        "announcements": results,
    }

    output = Path("data/announcements/tcs_manifest.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(output)

    downloaded = sum(
        item["document_status"] == "downloaded"
        for item in results
    )

    print(f"\nDownloaded {downloaded}/{len(results)} PDFs")
    print(f"Manifest saved: {output}")

    if not results or downloaded != len(results):
        raise SystemExit(
            "Document coverage is incomplete; inspect the manifest."
        )


if __name__ == "__main__":
    main()