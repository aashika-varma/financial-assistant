import hashlib
import re
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo


# Initial explicit mapping for our six-stock prototype.
# Later, move company names and aliases into an instrument registry.
COMPANY_NAMES = {
    "TCS": ["Tata Consultancy Services Limited"],
    "INFY": ["Infosys Limited"],
    "RELIANCE": ["Reliance Industries Limited"],
    "HDFCBANK": ["HDFC Bank Limited"],
    "ITC": ["ITC Limited"],
    "LT": [
        "Larsen & Toubro Limited",
        "Larsen and Toubro Limited",
    ],
}


class PlainTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value: str) -> str:
    parser = PlainTextParser()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


def normalize_name(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    return " ".join(re.findall(r"[a-z0-9]+", value))


NAME_TO_SYMBOL = {
    normalize_name(name): symbol
    for symbol, names in COMPANY_NAMES.items()
    for name in names
}


def normalize_entry(entry: dict, retrieved_at: str) -> dict:
    company_name = plain_text(entry.get("title", ""))
    summary = plain_text(entry.get("summary", ""))

    details, separator, subject = summary.rpartition("|SUBJECT:")
    if not separator:
        details = summary
        subject = ""

    raw_date = entry.get("published", "").strip()
    published_at = datetime.strptime(
        raw_date,
        "%d-%b-%Y %H:%M:%S",
    ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

    attachment_url = entry.get("link", "").strip() or None
    symbol = NAME_TO_SYMBOL.get(normalize_name(company_name))

    # Stable for an unchanged entry across repeated feed downloads.
    # Include the summary so a changed entry is retained separately.
    identity = "\n".join([
        company_name,
        published_at.isoformat(),
        attachment_url or "",
        summary,
    ])

    return {
        "source_entry_id": hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest(),
        "symbol": symbol,
        "company_name": company_name,
        "subject": subject.strip() or None,
        "details": details.strip(),
        "published_at": published_at.isoformat(),
        "published_raw": raw_date,
        "timezone_assumption": "Asia/Kolkata",
        "retrieved_at": retrieved_at,
        "attachment_url": attachment_url,
        "source": "nse_announcements_rss",
        "document_status": (
            "not_downloaded" if attachment_url else "no_attachment"
        ),
        "match_status": (
            "matched_company_name"
            if symbol
            else "not_in_prototype_mapping"
        ),
    }