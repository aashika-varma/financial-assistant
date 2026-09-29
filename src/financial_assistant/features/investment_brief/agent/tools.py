from datetime import date

from langchain_core.tools import tool
from psycopg import Error as DatabaseError
import psycopg


from financial_assistant.storage.rss_repository import (
    retrieve_rss_announcements,
)

from financial_assistant.context.retrievers.market import get_market_quotes


SOURCE = "samco_downloaded_nse_bhavcopy"


@tool
def get_portfolio_market_snapshot(
    symbols: list[str],
    trading_date: str,
) -> dict:
    """Retrieve stored NSE EQ prices for supplied portfolio symbols.

    Supports bulk retrieval: pass all requested symbols for the same
    trading date together in one call.

    trading_date must be YYYY-MM-DD and identify the exact requested
    trading session. Returns closing prices, daily percentage changes,
    and volume. Prices are historical end-of-day observations, not live.

    This tool does not retrieve news, earnings, corporate actions,
    quantities, or portfolio weights. An unavailable result means
    insufficient data, not that nothing meaningful happened.

    
    """
    try:
        session = date.fromisoformat(trading_date)
    except ValueError:
        return {
            "status": "invalid_request",
            "message": "trading_date must be a valid YYYY-MM-DD date.",
        }

    try:
        quotes = get_market_quotes(
            symbols=symbols,
            trading_date=session,
            source=SOURCE,
        )
    except ValueError:
        return {
            "status": "unavailable",
            "source": SOURCE,
            "requested_session": session.isoformat(),
            "message": (
                "A complete, valid snapshot could not be retrieved "
                "for the requested symbols and session."
            ),
        }
    except DatabaseError:
        return {
            "status": "source_error",
            "source": SOURCE,
            "requested_session": session.isoformat(),
            "message": "The market database could not complete the request.",
        }

    return {
        "status": "available",
        "source": SOURCE,
        "trading_date": session.isoformat(),
        "currency": "INR",
        "coverage": {
            "prices": "available",
            "news": "not_checked",
            "earnings": "not_checked",
            "corporate_actions": "not_checked",
            "allocation_changes": "not_checked",
        },
        "quotes": [
            quote.model_dump(mode="json")
            for quote in quotes
        ],
    }


@tool
def get_portfolio_announcements(
    symbols: list[str],
    start_at: str,
    end_at: str,
) -> dict:
    """Retrieve stored NSE RSS announcements for portfolio symbols.

    Supply timezone-aware ISO timestamps.
    The window includes start_at and excludes end_at.
    Results contain RSS summaries, not attachment contents.
    Empty results do not establish that no company events occurred.
    """
    try:
        return retrieve_rss_announcements(
            symbols=symbols,
            start_at=start_at,
            end_at=end_at,
        )
    except ValueError as exc:
        return {
            "status": "invalid_request",
            "error": str(exc),
        }
    except psycopg.Error:
        return {
            "status": "source_error",
            "error": "Could not retrieve stored RSS announcements.",
        }