import calendar
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

import feedparser


FEED_URL = (
    "https://nsearchives.nseindia.com"
    "/content/RSS/Online_announcements.xml"
)
OUTPUT_DIR = Path("data/announcements/rss")
MAX_BYTES = 10 * 1024 * 1024


def parsed_date(entry: dict) -> str | None:
    # Use feedparser's parsed date when available.
    value = (
        entry.get("published_parsed")
        or entry.get("updated_parsed")
    )
    if value is not None:
        return datetime.fromtimestamp(
            calendar.timegm(value),
            tz=timezone.utc,
        ).isoformat()

    # NSE-specific fallback for the format observed in this feed.
    raw_date = entry.get("published", "").strip()
    if not raw_date:
        return None

    try:
        local_time = datetime.strptime(
            raw_date,
            "%d-%b-%Y %H:%M:%S",
        )
    except ValueError:
        return None

    # The feed omits an explicit timezone.
    # Interpret this NSE source's timestamps as Asia/Kolkata.
    return (
        local_time
        .replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        .astimezone(timezone.utc)
        .isoformat()
    )


def main() -> None:
    request = Request(
        FEED_URL,
        headers={
            "User-Agent": "FinancialAssistantResearch/0.1",
            "Accept": (
                "application/rss+xml, application/xml, "
                "text/xml;q=0.9"
            ),
        },
    )

    with urlopen(request, timeout=30) as response:
        payload = response.read(MAX_BYTES + 1)
        content_type = response.headers.get("Content-Type", "")
        final_url = response.geturl()
        http_status = response.status

    if len(payload) > MAX_BYTES:
        raise ValueError("Feed response exceeds the 10 MB limit")

    retrieved_at = datetime.now(timezone.utc)
    stamp = retrieved_at.strftime("%Y%m%dT%H%M%S%fZ")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Preserve the actual response, even if it turns out to be
    # an error page rather than valid feed XML.
    raw_path = OUTPUT_DIR / f"nse_announcements_{stamp}.raw"
    raw_path.write_bytes(payload)

    feed = feedparser.parse(payload)
    entries = feed.get("entries", [])

    if not feed.get("version"):
        raise ValueError(
            "Response was not recognized as RSS/Atom. "
            f"Content-Type: {content_type}. Saved: {raw_path}"
        )

    warning = (
        str(feed.get("bozo_exception"))
        if feed.get("bozo")
        else None
    )

    entry_keys = sorted({
        key
        for entry in entries
        for key in entry.keys()
    })

    dates = [
        date
        for entry in entries
        if (date := parsed_date(entry)) is not None
    ]

    report = {
        "feed_url": FEED_URL,
        "final_url": final_url,
        "http_status": http_status,
        "content_type": content_type,
        "retrieved_at": retrieved_at.isoformat(),
        "feed_title": feed.get("feed", {}).get("title"),
        "feed_version": feed.get("version"),
        "parse_warning": warning,
        "entry_count": len(entries),
        "entry_fields": entry_keys,
        "entries_with_parsed_dates": len(dates),
        "earliest_parsed_date_utc": min(dates) if dates else None,
        "latest_parsed_date_utc": max(dates) if dates else None,
        "raw_file": str(raw_path),
    }

    # Keep every entry for inspection, including custom fields.
    inspection_path = OUTPUT_DIR / f"nse_announcements_{stamp}.json"
    inspection_path.write_text(
        json.dumps(
            {"report": report, "entries": entries},
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    print("FEED REPORT")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    print("\nFIRST 3 ENTRIES — ALL FIELDS")
    print(json.dumps(
        entries[:3],
        indent=2,
        ensure_ascii=False,
        default=str,
    ))

    print(f"\nSaved inspection: {inspection_path}")

    if warning:
        print("\nReview the parser warning before using this feed.")
    if not entries:
        print("\nEmpty feed: this does not establish complete coverage.")


if __name__ == "__main__":
    main()