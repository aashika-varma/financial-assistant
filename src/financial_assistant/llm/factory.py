import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from financial_assistant.config import get_settings


def get_llm() -> ChatOpenAI:
    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is missing")

    settings = get_settings().llm

    return ChatOpenAI(
        model=settings.model,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )