"""Shared application service for the CLI and future FastAPI routes."""
import json
from datetime import date, datetime, timedelta, timezone


def load_portfolio(user_id: str, holdings_date: date) -> list[dict]:
    from financial_assistant.storage.portfolio_repository import get_confirmed_portfolio
    return get_confirmed_portfolio(user_id=user_id, trading_date=holdings_date)


def build_request(
    versions,
    session,
    question,
    *,
    rss_enabled=False,
    web_search_enabled=False,
    now=None,
):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Generation time must be timezone-aware")
    symbols = sorted({h['symbol'] for v in versions for h in v['holdings']})
    if not symbols:
        raise ValueError("The confirmed portfolio has no holdings")
    context = [{
        'portfolio_version_id': v['portfolio_version_id'],
        'holdings_as_of': str(v['holdings_as_of']),
        'warnings': v.get('warnings', []),
        'holdings': [{'symbol': h['symbol'], 'quantity': str(h['quantity'])}
                     for h in v['holdings']],
    } for v in versions]

    if rss_enabled:
        news = (
            f"Stored Google News RSS window: {(now-timedelta(days=7)).isoformat()} "
            f"inclusive to {now.isoformat()} exclusive. "
            "Coverage depends on what was fetched in the nightly ingestion job. "
            "Pass the full 7-day window to get_portfolio_announcements — "
            "do not narrow the window unless the user specifies a shorter range."
        )
    else:
        news = "Stored news (get_portfolio_announcements) is not enabled."

    web = (
        "Live web search is enabled via search_portfolio_news. "
        "Use it for recent events not covered by stored news."
        if web_search_enabled
        else "Live web search is not connected."
    )

    return (
        f"Generated at: {now.isoformat()}.\n"
        f"Price session: {session.isoformat()} (historical closing prices, not live).\n"
        f"Portfolio symbols: {json.dumps(symbols)}.\n"
        f"Confirmed portfolio context: {json.dumps(context)}.\n"
        f"{news}\n{web}\n"
        "Keep holdings dates, price date and news dates separate. Holdings are snapshots, "
        "not proof of current positions. Preserve synthetic warnings.\n"
        f"User request: {question}"
    )


class BriefService:
    def __init__(self, *, rss_enabled=False, web_search_enabled=False):
        self.rss_enabled = rss_enabled
        self.web_search_enabled = web_search_enabled
        self._agent = None

    async def ask(self, user_id, session, question, *, brief=False, holdings_date=None):
        from financial_assistant.features.investment_brief.agent.factory import build_agent
        from financial_assistant.features.investment_brief.agent.orchestrator import handle_query
        from zoneinfo import ZoneInfo
        cutoff = holdings_date or datetime.now(ZoneInfo('Asia/Kolkata')).date()
        versions = load_portfolio(user_id, cutoff)
        request = build_request(
            versions,
            session,
            question,
            rss_enabled=self.rss_enabled,
            web_search_enabled=self.web_search_enabled,
        )
        if self._agent is None:
            self._agent = build_agent(
                include_rss=self.rss_enabled,
                include_web_search=self.web_search_enabled,
            )
        required = {'get_portfolio_market_snapshot'} if brief else set()
        if brief and self.rss_enabled:
            required.add('get_portfolio_announcements')
        # Web search is opportunistic — not required for every brief.
        return await handle_query(self._agent, request, required_tools=required)
