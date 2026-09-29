"""Google News RSS ingestion for portfolio symbols.

Fetches the Google News RSS feed for each supplied NSE symbol, normalises
entries into the same shape as rss_announcements, and upserts them into
the database using the existing rss_repository layer.

The source identifier is "google_news_rss" so results are clearly separated
from NSE RSS data in queries and the agent's coverage disclosures.

Google News RSS URL pattern (no API key required):
  https://news.google.com/rss/search?q=TCS+NSE+India&hl=en-IN&gl=IN&ceid=IN:en

Entries arrive in the feed's own published timestamp (RFC 2822).  We store
them as-is; the timezone is already UTC-offset in the feed.
"""

import hashlib
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen, Request

import feedparser

from financial_assistant.storage.database import get_connection
from financial_assistant.storage.rss_repository import aware_datetime
from psycopg.types.json import Jsonb


SOURCE = "google_news_rss"
_FEED_BASE = "https://news.google.com/rss/search"

# Polite delay between per-symbol requests so we don't hammer Google.
_INTER_REQUEST_DELAY_SECONDS = 2


def _feed_url(symbol: str, company_name: str | None = None) -> str:
    """Build a Google News RSS URL for an NSE symbol.

    Searching "<SYMBOL> NSE India" gives a good hit rate for Indian equities.
    If a company name is also known (from the instruments table) we include it
    for better recall on tickers that are ambiguous abbreviations.
    """
    query_parts = [symbol, "NSE", "India"]
    if company_name:
        query_parts.insert(0, company_name)
    query = " ".join(query_parts)
    params = urlencode({
        "q": query,
        "hl": "en-IN",
        "gl": "IN",
        "ceid": "IN:en",
    })
    return f"{_FEED_BASE}?{params}"


def _parse_published(entry: feedparser.FeedParserDict) -> datetime | None:
    """Return a timezone-aware datetime from a feedparser entry, or None."""
    # feedparser exposes published_parsed as a time.struct_time in UTC.
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return None


def _entry_id(symbol: str, title: str, published_at: datetime, link: str) -> str:
    """Stable content hash used as source_entry_id."""
    identity = "\n".join([symbol, title, published_at.isoformat(), link])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def fetch_news_for_symbol(
    symbol: str,
    company_name: str | None = None,
    max_entries: int = 20,
) -> list[dict]:
    """Fetch and normalise Google News RSS entries for one symbol.

    Returns a list of normalised announcement dicts ready for DB insertion.
    Entries older than 7 days are silently dropped to keep storage lean.
    """
    url = _feed_url(symbol, company_name)
    retrieved_at = datetime.now(timezone.utc)

    # feedparser handles the HTTP request internally but doesn't set a UA.
    # Some proxies block the default UA; provide a neutral one.
    req = Request(url, headers={"User-Agent": "financial-assistant/1.0 (RSS reader)"})
    try:
        with urlopen(req, timeout=15) as response:
            raw = response.read()
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch Google News RSS for {symbol}: {exc}"
        ) from exc

    feed = feedparser.parse(raw)

    if feed.bozo and not feed.entries:
        raise RuntimeError(
            f"Feed parse error for {symbol}: {feed.bozo_exception}"
        )

    cutoff = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # Keep last 7 days only.
    from datetime import timedelta
    oldest_allowed = cutoff - timedelta(days=7)

    results = []
    for entry in feed.entries[:max_entries]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        summary = (entry.get("summary") or title).strip()

        published_at = _parse_published(entry)
        if published_at is None:
            # Can't store without a timestamp — skip.
            continue

        if published_at < oldest_allowed:
            continue

        results.append({
            "source": SOURCE,
            "source_entry_id": _entry_id(symbol, title, published_at, link),
            "symbol": symbol,
            # Google News titles are the article headline, not a company name.
            "company_name": company_name or symbol,
            "subject": title,
            "details": summary,
            "published_at": published_at.isoformat(),
            "attachment_url": link or None,
            "retrieved_at": retrieved_at.isoformat(),
            "payload": {
                "feed_url": url,
                "title": title,
                "link": link,
                "summary": summary,
                "published_at": published_at.isoformat(),
                "retrieved_at": retrieved_at.isoformat(),
                "symbol": symbol,
                "source": SOURCE,
            },
        })

    return results


def _lookup_company_names(symbols: list[str]) -> dict[str, str]:
    """Return {symbol: company_name} for symbols present in instruments."""
    if not symbols:
        return {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (symbol) symbol, isin
                FROM instruments
                WHERE exchange = 'NSE'
                  AND series = 'EQ'
                  AND symbol = ANY(%s)
                ORDER BY symbol, instrument_id DESC
                """,
                (symbols,),
            )
            # We only have symbol in instruments; company name isn't stored.
            # Return an empty mapping — callers will use symbol-only queries.
            return {}


def save_news_announcements(announcements: list[dict]) -> dict:
    """Upsert a batch of normalised Google News entries into rss_announcements.

    Uses ON CONFLICT to update first_seen_at / last_seen_at for repeated
    entries (same article appearing in multiple fetches).

    Returns a summary dict: {saved, skipped, total}.
    """
    if not announcements:
        return {"saved": 0, "skipped": 0, "total": 0}

    saved = 0
    skipped = 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            for item in announcements:
                try:
                    retrieved_at = aware_datetime(item["retrieved_at"])
                    published_at = aware_datetime(item["published_at"])
                except ValueError:
                    skipped += 1
                    continue

                cur.execute(
                    """
                    INSERT INTO rss_announcements (
                        source, source_entry_id, symbol,
                        company_name, subject, details,
                        published_at, attachment_url,
                        first_seen_at, last_seen_at, payload
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (source, source_entry_id)
                    DO UPDATE SET
                        last_seen_at = GREATEST(
                            rss_announcements.last_seen_at,
                            EXCLUDED.last_seen_at
                        ),
                        first_seen_at = LEAST(
                            rss_announcements.first_seen_at,
                            EXCLUDED.first_seen_at
                        )
                    """,
                    (
                        item["source"],
                        item["source_entry_id"],
                        item.get("symbol"),
                        item["company_name"],
                        item.get("subject"),
                        item["details"],
                        published_at,
                        item.get("attachment_url"),
                        retrieved_at,
                        retrieved_at,
                        Jsonb(item["payload"]),
                    ),
                )
                saved += 1

    return {"saved": saved, "skipped": skipped, "total": len(announcements)}


def ingest_news_for_symbols(
    symbols: list[str],
    *,
    max_entries_per_symbol: int = 20,
    delay_seconds: float = _INTER_REQUEST_DELAY_SECONDS,
    dry_run: bool = False,
) -> dict:
    """Fetch Google News RSS for each symbol and upsert into Neon.

    Returns a per-symbol report plus totals.
    """
    if not symbols:
        raise ValueError("At least one symbol is required")

    report = {
        "symbols_requested": len(symbols),
        "results": {},
        "totals": {"fetched": 0, "saved": 0, "skipped": 0, "errors": 0},
    }

    for i, symbol in enumerate(symbols):
        if i > 0:
            time.sleep(delay_seconds)

        try:
            entries = fetch_news_for_symbol(
                symbol,
                max_entries=max_entries_per_symbol,
            )
        except Exception as exc:
            report["results"][symbol] = {"status": "error", "error": str(exc)}
            report["totals"]["errors"] += 1
            continue

        report["totals"]["fetched"] += len(entries)

        if dry_run:
            report["results"][symbol] = {
                "status": "dry_run",
                "fetched": len(entries),
                "sample": [e["subject"] for e in entries[:3]],
            }
            continue

        try:
            save_result = save_news_announcements(entries)
        except Exception as exc:
            report["results"][symbol] = {
                "status": "db_error",
                "fetched": len(entries),
                "error": str(exc),
            }
            report["totals"]["errors"] += 1
            continue

        report["results"][symbol] = {
            "status": "ok",
            "fetched": len(entries),
            **save_result,
        }
        report["totals"]["saved"] += save_result["saved"]
        report["totals"]["skipped"] += save_result["skipped"]

    return report
