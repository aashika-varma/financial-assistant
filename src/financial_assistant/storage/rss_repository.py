import hashlib
import json
from datetime import datetime
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from financial_assistant.storage.database import get_connection


SOURCE = "nse_announcements_rss"


def aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Timestamp must include a timezone: {value}")
    return parsed


def save_rss_snapshot(path: Path) -> dict:
    file_bytes = path.read_bytes()
    data = json.loads(file_bytes)
    report = data["feed_report"]
    announcements = data["announcements"]

    if data.get("errors"):
        raise ValueError("Resolve normalization errors before saving")

    if report.get("parse_warning"):
        raise ValueError("Resolve feed parser warnings before saving")

    if report.get("http_status") != 200:
        raise ValueError("Expected a successful feed response")

    if len(announcements) != data["normalized_count"]:
        raise ValueError("Normalized count does not match records")

    retrieved_at = aware_datetime(report["retrieved_at"])
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # Validate timestamps and source before starting database writes.
    for item in announcements:
        if item["source"] != SOURCE:
            raise ValueError("Unexpected announcement source")
        aware_datetime(item["published_at"])

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO rss_feed_snapshots (
                    file_sha256, source_file, feed_url,
                    retrieved_at, entry_count, normalized_count
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (file_sha256) DO NOTHING
                RETURNING snapshot_id
                """,
                (
                    file_hash,
                    path.name,
                    report["feed_url"],
                    retrieved_at,
                    report["entry_count"],
                    len(announcements),
                ),
            )
            inserted = cursor.fetchone()

            if inserted is None:
                cursor.execute(
                    """
                    SELECT snapshot_id
                    FROM rss_feed_snapshots
                    WHERE file_sha256 = %s
                    """,
                    (file_hash,),
                )
                return {
                    "snapshot_id": cursor.fetchone()[0],
                    "status": "already_saved",
                    "announcement_count": len(announcements),
                }

            snapshot_id = inserted[0]

            for item in announcements:
                cursor.execute(
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
                        first_seen_at = LEAST(
                            rss_announcements.first_seen_at,
                            EXCLUDED.first_seen_at
                        ),
                        last_seen_at = GREATEST(
                            rss_announcements.last_seen_at,
                            EXCLUDED.last_seen_at
                        )
                    RETURNING announcement_id
                    """,
                    (
                        item["source"],
                        item["source_entry_id"],
                        item.get("symbol"),
                        item["company_name"],
                        item.get("subject"),
                        item["details"],
                        aware_datetime(item["published_at"]),
                        item.get("attachment_url"),
                        retrieved_at,
                        retrieved_at,
                        Jsonb(item),
                    ),
                )
                announcement_id = cursor.fetchone()[0]

                cursor.execute(
                    """
                    INSERT INTO rss_snapshot_entries (
                        snapshot_id, announcement_id
                    )
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (snapshot_id, announcement_id),
                )

    return {
        "snapshot_id": snapshot_id,
        "status": "saved",
        "announcement_count": len(announcements),
    }


def retrieve_rss_announcements(
    symbols: list[str],
    start_at: str,
    end_at: str,
) -> dict:
    """Retrieve publications in [start_at, end_at)."""
    requested = sorted({
        symbol.strip().upper()
        for symbol in symbols
        if symbol.strip()
    })
    if not requested:
        raise ValueError("At least one symbol is required")

    start = aware_datetime(start_at)
    end = aware_datetime(end_at)
    if start >= end:
        raise ValueError("start_at must be earlier than end_at")

    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    announcement_id, symbol, company_name,
                    subject, details, published_at,
                    attachment_url, source, first_seen_at
                FROM rss_announcements
                WHERE symbol = ANY(%s)
                  AND published_at >= %s
                  AND published_at < %s
                ORDER BY published_at, announcement_id
                """,
                (requested, start, end),
            )
            rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS stored_snapshot_count,
                    MAX(retrieved_at) AS latest_collection_at
                FROM rss_feed_snapshots
                """
            )
            collection = cursor.fetchone()

    for row in rows:
        row["published_at"] = row["published_at"].isoformat()
        row["first_seen_at"] = row["first_seen_at"].isoformat()
        row["content_scope"] = "rss_summary"
        row["attachment_read"] = False

    latest = collection["latest_collection_at"]

    return {
        "status": (
            "available"
            if collection["stored_snapshot_count"]
            else "not_collected"
        ),
        "source": SOURCE,
        "requested_symbols": requested,
        "window": {
            "start_inclusive": start.isoformat(),
            "end_exclusive": end.isoformat(),
        },
        "coverage_status": "feed_snapshot_only",
        "stored_snapshot_count": collection["stored_snapshot_count"],
        "latest_collection_at": latest.isoformat() if latest else None,
        "count": len(rows),
        "announcements": rows,
        "limitations": [
            "Stored snapshots do not establish complete window coverage.",
            "Company matching currently covers six configured equities.",
            "Attachment contents have not been read by this tool.",
        ],
    }