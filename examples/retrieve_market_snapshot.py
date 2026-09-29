import json
from datetime import date

from financial_assistant.context.retrievers.market import get_market_quotes


def main() -> None:
    source = "samco_downloaded_nse_bhavcopy"

    quotes = get_market_quotes(
        symbols=["TCS", "INFY", "RELIANCE"],
        trading_date=date(2026, 9, 25),
        source=source,
    )

    result = {
        "source": source,
        "quotes": [
            quote.model_dump(mode="json")
            for quote in quotes
        ],
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()