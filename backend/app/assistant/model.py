from langchain_openai import ChatOpenAI

from app.core.config import settings


def build_chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.require_openrouter_api_key(),
        base_url=settings.openrouter_base_url,
    )
