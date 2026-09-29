import json

from financial_assistant.features.investment_brief.agent.tools import (
    get_portfolio_market_snapshot,
)


def main() -> None:
    result = get_portfolio_market_snapshot.invoke({
        "symbols": ["TCS", "INFY", "RELIANCE"],
        "trading_date": "2026-09-25",
    })

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()