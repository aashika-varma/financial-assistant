import csv
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")


def load_announcements(
    path: Path,
    symbols: list[str],
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Read NSE announcement metadata for an inclusive date window."""
    if start_date > end_date:
        raise ValueError("start_date must not exceed end_date")

    requested = {symbol.strip().upper() for symbol in symbols}
    announcements = []

    required = {
        "SYMBOL",
        "COMPANY NAME",
        "SUBJECT",
        "DETAILS",
        "BROADCAST DATE/TIME",
        "ATTACHMENT",
    }

    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if missing := required - set(reader.fieldnames or []):
            raise ValueError(f"Missing CSV columns: {sorted(missing)}")

        for row_number, row in enumerate(reader, start=2):
            symbol = row["SYMBOL"].strip().upper()

            if symbol not in requested:
                continue

            try:
                published_at = datetime.strptime(
                    row["BROADCAST DATE/TIME"].strip(),
                    "%d-%b-%Y %H:%M:%S",
                ).replace(tzinfo=MARKET_TIMEZONE)
            except ValueError as error:
                raise ValueError(
                    f"Invalid broadcast timestamp on CSV row {row_number}"
                ) from error

            if not start_date <= published_at.date() <= end_date:
                continue

            announcements.append({
                "symbol": symbol,
                "company_name": row["COMPANY NAME"].strip(),
                "subject": row["SUBJECT"].strip(),
                "details": row["DETAILS"].strip(),
                "published_at": published_at.isoformat(),
                "attachment_url": row["ATTACHMENT"].strip() or None,
                "source": "nse_announcements_csv",
                "source_file": path.name,
                "source_row": row_number,
                "document_status": "not_downloaded",
            })

    return sorted(
        announcements,
        key=lambda item: item["published_at"],
    )