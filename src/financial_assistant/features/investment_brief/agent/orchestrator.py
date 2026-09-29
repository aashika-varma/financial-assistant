import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from financial_assistant.config import get_settings

from financial_assistant.observability.logger import get_logger


logger = get_logger(__name__)


async def handle_query(agent, question: str, *, required_tools=None) -> dict:
    if not question.strip():
        raise ValueError("Question cannot be empty")

    logger.info("Starting investment brief request")
    settings = get_settings().investment_brief

    result = await asyncio.wait_for(
        agent.ainvoke(
            {"messages": [{"role": "user", "content": question}]},
            config={"recursion_limit": settings.recursion_limit},
        ),
        timeout=settings.timeout_seconds,
    )

    messages = result["messages"]

    for message in messages:
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls:
                logger.info(
                    "Tool requested: %s | arguments: %s",
                    tool_call["name"],
                    tool_call["args"],
                )

    tools_used = [
        message.name
        for message in messages
        if isinstance(message, ToolMessage)
    ]

    missing = set(required_tools or ()) - set(tools_used)
    if missing:
        raise RuntimeError(f"Required tools were not called: {sorted(missing)}")

    final_message = messages[-1]

    if not isinstance(final_message, AIMessage) or final_message.tool_calls:
        raise RuntimeError("The agent did not produce a final answer")

    logger.info("Completed brief; tools used: %s", tools_used)

    return {
        "answer": final_message.content,
        "tools_used": tools_used,
    }
