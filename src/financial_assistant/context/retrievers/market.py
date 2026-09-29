from datetime import date

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