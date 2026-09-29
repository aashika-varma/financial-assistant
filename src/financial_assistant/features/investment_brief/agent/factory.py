from langchain.agents import create_agent

from financial_assistant.llm.factory import get_llm
from financial_assistant.features.investment_brief.agent.middleware import (
    build_middleware,
)
from financial_assistant.features.investment_brief.agent.prompts import (
    SYSTEM_PROMPT,
)
from financial_assistant.features.investment_brief.agent.tools import (
    get_portfolio_market_snapshot, get_portfolio_announcements
)


def build_agent(*, include_rss: bool = False):
    tools = [get_portfolio_market_snapshot]
    if include_rss:
        tools.append(get_portfolio_announcements)
    return create_agent(
        model=get_llm(),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=build_middleware(),
    )
