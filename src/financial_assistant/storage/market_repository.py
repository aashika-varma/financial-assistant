import hashlib
from datetime import date
from pathlib import Path

from financial_assistant.schemas.market import BhavcopyQuote
from financial_assistant.storage.database import get_connection


SOURCE = "samco_downloaded_nse_bhavcopy"


def save_quotes(
    quotes: list[BhavcopyQuote],
    source_file: Path,
    target_session: date,
) -> int:
    """Save one validated batch and return its ingestion run ID.

    Portfolio-scoped path: expects a pre-filtered list of symbols.
    For full-market ingestion (all NSE EQ rows) use save_all_quotes.
    """
    if not quotes:
        raise ValueError("Cannot save an empty batch")

    if any(quote.date != target_session for quote in quotes):
        raise ValueError("Quote dates do not match the target session")

    identities = [
        (quote.exchange, quote.isin, quote.series)
        for quote in quotes
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate instruments in batch")

    with source_file.open("rb") as file:
        file_hash = hashlib.file_digest(file, "sha256").hexdigest()

    # Commit the run first so a failed write can still be recorded.
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ingestion_runs (
                    source, source_file, file_sha256, target_session
                )
                VALUES (%s, %s, %s, %s)
                RETURNING ingestion_run_id
                """,
                (
                    SOURCE,
                    source_file.name,
                    file_hash,
                    target_session,
                ),
            )
            run_id = cursor.fetchone()[0]

    try:
        # All quote writes succeed together or roll back together.
        with get_connection() as connection:
            with connection.cursor() as cursor:
                for quote in quotes:
                    cursor.execute(
                        """
                        INSERT INTO instruments (
                            exchange, isin, series, symbol
                        )
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (exchange, isin, series)
                        DO UPDATE SET symbol = EXCLUDED.symbol
                        RETURNING instrument_id
                        """,
                        (
                            quote.exchange,
                            quote.isin,
                            quote.series,
                            quote.symbol,
                        ),
                    )
                    instrument_id = cursor.fetchone()[0]

                    cursor.execute(
                        """
                        INSERT INTO daily_quotes (
                            instrument_id, trading_date, source,
                            open, high, low, close, prev_close,
                            pct_change, volume, ingestion_run_id
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (
                            instrument_id, trading_date, source
                        )
                        DO UPDATE SET
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            prev_close = EXCLUDED.prev_close,
                            pct_change = EXCLUDED.pct_change,
                            volume = EXCLUDED.volume,
                            ingestion_run_id = EXCLUDED.ingestion_run_id,
                            updated_at = NOW()
                        """,
                        (
                            instrument_id,
                            quote.date,
                            SOURCE,
                            quote.open,
                            quote.high,
                            quote.low,
                            quote.close,
                            quote.prev_close,
                            quote.pct_change,
                            quote.volume,
                            run_id,
                        ),
                    )

                cursor.execute(
                    """
                    UPDATE ingestion_runs
                    SET status = 'succeeded',
                        row_count = %s,
                        completed_at = NOW()
                    WHERE ingestion_run_id = %s
                    """,
                    (len(quotes), run_id),
                )

    except Exception as error:
        try:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE ingestion_runs
                        SET status = 'failed',
                            error_message = %s,
                            completed_at = NOW()
                        WHERE ingestion_run_id = %s
                        """,
                        (type(error).__name__, run_id),
                    )
        except Exception:
            # Preserve the original write error if status recording fails.
            pass
        raise

    return run_id


def save_all_quotes(
    quotes: list[BhavcopyQuote],
    source_file: Path,
    target_session: date,
) -> int:
    """Upsert the full NSE EQ universe and return the ingestion run ID.

    Designed for the daily automated pipeline that ingests every EQ row
    from the bhavcopy, not just portfolio symbols.  Uses executemany for
    the instrument upsert then a single bulk-copy INSERT for quotes so
    that ~2 000 rows commit in one round-trip rather than 4 000.

    The run is recorded as 'started' before any writes begin; on failure
    it is updated to 'failed' so the scheduler can detect partial runs.
    A duplicate file_sha256 (identical download re-submitted) is rejected
    immediately so the same file cannot be imported twice.
    """
    if not quotes:
        raise ValueError("Cannot save an empty batch")

    if any(quote.date != target_session for quote in quotes):
        raise ValueError("Quote dates do not match the target session")

    identities = [(q.exchange, q.isin, q.series) for q in quotes]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate instruments in batch")

    with source_file.open("rb") as file:
        file_hash = hashlib.file_digest(file, "sha256").hexdigest()

    # --- record the run before touching market data ---
    with get_connection() as connection:
        with connection.cursor() as cursor:
            # Reject a duplicate file so re-runs of the same download
            # don't silently succeed and count as a new ingestion.
            cursor.execute(
                """
                SELECT ingestion_run_id, status
                FROM ingestion_runs
                WHERE file_sha256 = %s
                """,
                (file_hash,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                prior_id, prior_status = existing
                raise ValueError(
                    f"File already ingested (run {prior_id}, "
                    f"status={prior_status}). "
                    "Pass a different session date or a new download."
                )

            cursor.execute(
                """
                INSERT INTO ingestion_runs (
                    source, source_file, file_sha256, target_session
                )
                VALUES (%s, %s, %s, %s)
                RETURNING ingestion_run_id
                """,
                (SOURCE, source_file.name, file_hash, target_session),
            )
            run_id = cursor.fetchone()[0]

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                # Step 1 – upsert instruments and collect their IDs.
                # executemany keeps the round-trips low while still
                # giving us the RETURNING id for each row.
                instrument_ids: dict[str, int] = {}  # isin -> id

                for quote in quotes:
                    cursor.execute(
                        """
                        INSERT INTO instruments (
                            exchange, isin, series, symbol
                        )
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (exchange, isin, series)
                        DO UPDATE SET symbol = EXCLUDED.symbol
                        RETURNING instrument_id
                        """,
                        (
                            quote.exchange,
                            quote.isin,
                            quote.series,
                            quote.symbol,
                        ),
                    )
                    instrument_ids[quote.isin] = cursor.fetchone()[0]

                # Step 2 – bulk-upsert all daily_quotes rows.
                cursor.executemany(
                    """
                    INSERT INTO daily_quotes (
                        instrument_id, trading_date, source,
                        open, high, low, close, prev_close,
                        pct_change, volume, ingestion_run_id
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (instrument_id, trading_date, source)
                    DO UPDATE SET
                        open             = EXCLUDED.open,
                        high             = EXCLUDED.high,
                        low              = EXCLUDED.low,
                        close            = EXCLUDED.close,
                        prev_close       = EXCLUDED.prev_close,
                        pct_change       = EXCLUDED.pct_change,
                        volume           = EXCLUDED.volume,
                        ingestion_run_id = EXCLUDED.ingestion_run_id,
                        updated_at       = NOW()
                    """,
                    [
                        (
                            instrument_ids[quote.isin],
                            quote.date,
                            SOURCE,
                            quote.open,
                            quote.high,
                            quote.low,
                            quote.close,
                            quote.prev_close,
                            quote.pct_change,
                            quote.volume,
                            run_id,
                        )
                        for quote in quotes
                    ],
                )

                cursor.execute(
                    """
                    UPDATE ingestion_runs
                    SET status       = 'succeeded',
                        row_count    = %s,
                        completed_at = NOW()
                    WHERE ingestion_run_id = %s
                    """,
                    (len(quotes), run_id),
                )

    except Exception as error:
        try:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE ingestion_runs
                        SET status        = 'failed',
                            error_message = %s,
                            completed_at  = NOW()
                        WHERE ingestion_run_id = %s
                        """,
                        (type(error).__name__, run_id),
                    )
        except Exception:
            pass
        raise

    return run_id
