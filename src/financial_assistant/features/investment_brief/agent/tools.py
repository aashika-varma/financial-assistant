import os
from datetime import date

from langchain_core.tools import tool
from psycopg import Error as DatabaseError
import psycopg


from financial_assistant.storage.rss_repository import (
    retrieve_rss_announcements,
)

from financial_assistant.context.retrievers.market import get_market_quotes, get_52_week_range


SOURCE = "samco_downloaded_nse_bhavcopy"


@tool
def get_portfolio_market_snapshot(
    symbols: list[str],
    trading_date: str,
    holdings: list[dict] | None = None,
) -> dict:
    """Retrieve stored NSE EQ prices for supplied portfolio symbols.

    Supports bulk retrieval: pass all requested symbols for the same
    trading date together in one call.

    trading_date must be YYYY-MM-DD and identify the exact requested
    trading session. Returns closing prices, daily percentage changes,
    volume, 52-week high/low, and — when holdings are supplied —
    current market value and portfolio weight for each position.

    holdings: optional list of {symbol, quantity} dicts from the
    confirmed portfolio context. Pass them to get portfolio weights.
    Quantities must be positive numbers (strings or ints accepted).

    Prices are historical end-of-day observations, not live.
    This tool does not retrieve news, earnings, or corporate actions.
    An unavailable result means insufficient data, not a quiet market.
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

    # 52-week range — best-effort, silently omitted per symbol if no data.
    try:
        week52 = get_52_week_range(symbols=symbols, as_of=session, source=SOURCE)
    except Exception:
        week52 = {}

    # Build quantity lookup from supplied holdings.
    qty_by_symbol: dict[str, float] = {}
    if holdings:
        for h in holdings:
            sym = str(h.get("symbol", "")).strip().upper()
            try:
                qty_by_symbol[sym] = float(h.get("quantity", 0))
            except (TypeError, ValueError):
                pass

    # Compute portfolio weights if we have quantities.
    quote_rows = [q.model_dump(mode="json") for q in quotes]
    if qty_by_symbol:
        total_value = sum(
            float(q["close"]) * qty_by_symbol.get(q["symbol"], 0)
            for q in quote_rows
        )
        for q in quote_rows:
            qty = qty_by_symbol.get(q["symbol"], 0)
            market_value = round(float(q["close"]) * qty, 2)
            q["quantity"] = qty
            q["market_value_inr"] = market_value
            q["portfolio_weight_pct"] = (
                round(market_value / total_value * 100, 2)
                if total_value else None
            )
        # Attach total for the agent's reference.
        portfolio_total_inr = round(total_value, 2)
    else:
        portfolio_total_inr = None

    # Attach 52-week range to each quote row.
    for q in quote_rows:
        r = week52.get(q["symbol"])
        if r:
            q["week52_high"] = float(r["week52_high"])
            q["week52_low"] = float(r["week52_low"])
            q["week52_days_of_data"] = r["days_of_data"]
            # How far is close from 52-week high? Negative = below high.
            q["pct_from_52w_high"] = round(
                (float(q["close"]) - float(r["week52_high"]))
                / float(r["week52_high"]) * 100, 2
            )

    return {
        "status": "available",
        "source": SOURCE,
        "trading_date": session.isoformat(),
        "currency": "INR",
        "portfolio_total_inr": portfolio_total_inr,
        "coverage": {
            "prices": "available",
            "week52_range": "available" if week52 else "no_data",
            "portfolio_weights": "available" if qty_by_symbol else "not_supplied",
            "news": "not_checked",
            "earnings": "not_checked",
            "corporate_actions": "not_checked",
        },
        "quotes": quote_rows,
    }


@tool
def get_portfolio_announcements(
    symbols: list[str],
    start_at: str,
    end_at: str,
) -> dict:
    """Retrieve stored Google News RSS articles for portfolio symbols.

    Supply timezone-aware ISO timestamps.
    The window includes start_at and excludes end_at.
    Results are news headlines and summaries fetched from Google News;
    they are not official NSE exchange announcements.
    Empty results mean no stored articles for this window — not that
    no news exists.
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
            "error": "Could not retrieve stored news articles.",
        }


@tool
def search_portfolio_news(
    symbols: list[str],
    query: str,
) -> dict:
    """Search the live web for recent news about portfolio symbols.

    Use this tool when stored news is insufficient, stale, or when the
    user asks about very recent events (today or the last 24 hours).

    symbols: the portfolio NSE symbols this search relates to.
    query: a specific, focused search query. Include the company name
           and/or NSE symbol plus the topic (e.g. "TCS Q2 results 2026",
           "Infosys management change", "Reliance Industries acquisition").

    Returns web search results with titles, URLs and snippets.
    These are live web results — not stored data — and may include
    opinion, speculation or inaccurate sources. Treat as supplementary
    context only and disclose the source in the brief.
    Do not fabricate news not present in the results.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {
            "status": "unavailable",
            "error": "TAVILY_API_KEY is not configured.",
        }

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)

        response = client.search(
            query=query,
            search_depth="basic",
            max_results=5,
            include_domains=[
                "economictimes.indiatimes.com",
                "livemint.com",
                "business-standard.com",
                "moneycontrol.com",
                "financialexpress.com",
                "reuters.com",
                "bloomberg.com",
                "nseindia.com",
            ],
        )

        results = response.get("results", [])

        return {
            "status": "available",
            "source": "tavily_web_search",
            "query": query,
            "symbols": symbols,
            "coverage": "live_web",
            "result_count": len(results),
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                    "published_date": r.get("published_date"),
                }
                for r in results
            ],
            "limitations": [
                "Live web results — accuracy not guaranteed.",
                "Sources may include opinion or speculation.",
                "Disclose this as a web search result in the brief.",
            ],
        }

    except Exception as exc:
        return {
            "status": "source_error",
            "error": f"Web search failed: {type(exc).__name__}",
        }
