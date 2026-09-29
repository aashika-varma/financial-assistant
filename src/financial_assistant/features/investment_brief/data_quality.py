from datetime import date

from financial_assistant.schemas.market import MarketQuote


def assess_quote_dates(
    quotes: list[MarketQuote],
    target_session: date,
) -> dict:
    """Check whether each quote matches the requested trading session."""
    issues = []

    for quote in quotes:
        if quote.date < target_session:
            issues.append({
                "symbol": quote.symbol,
                "reason": "older_than_target",
                "actual_date": quote.date.isoformat(),
            })
        elif quote.date > target_session:
            issues.append({
                "symbol": quote.symbol,
                "reason": "newer_than_target",
                "actual_date": quote.date.isoformat(),
            })

    if not quotes:
        status = "missing"
    elif issues:
        status = "date_mismatch"
    else:
        status = "matches_target"

    return {
        "status": status,
        "target_session": target_session.isoformat(),
        "issues": issues,
    }