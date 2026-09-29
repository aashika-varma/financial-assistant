import argparse
from datetime import date
from pathlib import Path

from financial_assistant.ingestion.bhavcopy import load_bhavcopy_zip
from financial_assistant.storage.database import get_connection
from financial_assistant.storage.market_repository import (
    SOURCE,
    save_quotes,
)


SYMBOLS = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "ITC", "LT"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--session", type=date.fromisoformat, required=True)
    args = parser.parse_args()

    quotes = load_bhavcopy_zip(args.file, SYMBOLS, args.session)

    run_id = save_quotes(
        quotes=quotes,
        source_file=args.file,
        target_session=args.session,
    )

    print(f"Ingestion run {run_id}: saved {len(quotes)} quotes")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT i.symbol, q.trading_date, q.close
                FROM daily_quotes AS q
                JOIN instruments AS i
                    ON i.instrument_id = q.instrument_id
                WHERE q.trading_date = %s
                  AND q.source = %s
                  AND i.exchange = 'NSE'
                  AND i.series = 'EQ'
                  AND i.isin = ANY(%s)
                ORDER BY i.symbol
                """,
                (
                    args.session,
                    SOURCE,
                    [quote.isin for quote in quotes],
                ),
            )
            rows = cursor.fetchall()

    print(f"Read back {len(rows)} database rows")
    for symbol, trading_date, close in rows:
        print(f"{symbol}: {trading_date} | close={close}")


if __name__ == "__main__":
    main()