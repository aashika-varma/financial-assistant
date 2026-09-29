from langchain.agents import create_agent

from financial_assistant.llm.factory import get_llm
from financial_assistant.features.investment_brief.agent.middleware import (
    build_middleware,
)
from financial_assistant.features.investment_brief.agent.prompts import (
    SYSTEM_PROMPT,
)
from financial_assistant.features.investment_brief.agent.tools import (
    get_portfolio_market_snapshot,
    get_portfolio_announcements,
    search_portfolio_news,
)


def build_agent(
    *,
    include_rss: bool = False,
    include_web_search: bool = False,
):
    tools = [get_portfolio_market_snapshot]
    if include_rss:
        tools.append(get_portfolio_announcements)
    if include_web_search:
        tools.append(search_portfolio_news)
    return create_agent(
        model=get_llm(),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=build_middleware(),
    )
