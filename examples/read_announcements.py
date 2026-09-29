import json
from datetime import date
from pathlib import Path

from financial_assistant.ingestion.announcements import load_announcements


def main() -> None:
    announcements = load_announcements(
        path=Path(
            "data/announcements/CF-AN-equities-TCS-29-Sep-2026.csv"
        ),
        symbols=["TCS"],
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 25),
    )

    print(f"Found {len(announcements)} announcements")
    print(json.dumps(announcements, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()