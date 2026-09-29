from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)

from financial_assistant.config import get_settings


def build_middleware():
    settings = get_settings().investment_brief
    middleware = []

    if settings.model_call_limit is not None:
        middleware.append(
            ModelCallLimitMiddleware(
                run_limit=settings.model_call_limit,
                exit_behavior="error",
            )
        )

    if settings.tool_call_limit is not None:
        middleware.append(
            ToolCallLimitMiddleware(
                run_limit=settings.tool_call_limit,
                exit_behavior="error",
            )
        )

    return middleware