from datetime import date, timedelta
from decimal import Decimal

from psycopg.rows import dict_row

from financial_assistant.schemas.market import BhavcopyQuote
from financial_assistant.storage.database import get_connection


def get_market_quotes(
    symbols: list[str],
    trading_date: date,
    source: str,
) -> list[BhavcopyQuote]:
    """Retrieve all requested NSE EQ quotes for an exact session."""
    requested = list(dict.fromkeys(
        symbol.strip().upper() for symbol in symbols
    ))

    if not requested or any(not symbol for symbol in requested):
        raise ValueError("Provide at least one non-empty stock symbol")

    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    i.symbol,
                    i.exchange,
                    i.series,
                    i.isin,
                    q.trading_date AS date,
                    q.open,
                    q.high,
                    q.low,
                    q.close,
                    q.prev_close,
                    q.pct_change,
                    q.volume
                FROM daily_quotes AS q
                JOIN instruments AS i
                    ON i.instrument_id = q.instrument_id
                WHERE i.exchange = 'NSE'
                  AND i.series = 'EQ'
                  AND i.symbol = ANY(%s)
                  AND q.trading_date = %s
                  AND q.source = %s
                """,
                (requested, trading_date, source),
            )
            rows = cursor.fetchall()

    quotes_by_symbol = {}

    for row in rows:
        quote = BhavcopyQuote.model_validate(row)

        if quote.symbol in quotes_by_symbol:
            raise ValueError(
                f"Ambiguous instrument for symbol: {quote.symbol}"
            )

        quotes_by_symbol[quote.symbol] = quote

    missing = set(requested) - quotes_by_symbol.keys()

    if missing:
        raise ValueError(
            f"Missing quotes for {trading_date} from {source}: "
            f"{sorted(missing)}"
        )

    return [quotes_by_symbol[symbol] for symbol in requested]


def get_52_week_range(
    symbols: list[str],
    as_of: date,
    source: str,
) -> dict[str, dict]:
    """Compute 52-week high/low for each symbol from stored daily_quotes.

    Uses up to 365 calendar days of data ending on as_of (inclusive).
    Returns {symbol: {week52_high, week52_low, days_of_data}} for each
    symbol that has at least one stored row in the window.
    Symbols with no data are omitted from the result.
    """
    if not symbols:
        return {}

    start = as_of - timedelta(days=365)

    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    i.symbol,
                    MAX(q.high)          AS week52_high,
                    MIN(q.low)           AS week52_low,
                    COUNT(q.trading_date) AS days_of_data
                FROM daily_quotes AS q
                JOIN instruments AS i
                    ON i.instrument_id = q.instrument_id
                WHERE i.exchange = 'NSE'
                  AND i.series = 'EQ'
                  AND i.symbol = ANY(%s)
                  AND q.trading_date >= %s
                  AND q.trading_date <= %s
                  AND q.source = %s
                GROUP BY i.symbol
                """,
                (symbols, start, as_of, source),
            )
            rows = cursor.fetchall()

    return {
        row["symbol"]: {
            "week52_high": row["week52_high"],
            "week52_low": row["week52_low"],
            "days_of_data": row["days_of_data"],
        }
        for row in rows
    }