"""Chat model construction for the OpenRouter gateway.

``OpenRouterProvider`` has no ``base_url`` parameter, so the only way to honor
``settings.openrouter_base_url`` — and to keep the SDK from reading
``os.environ`` on its own — is to hand it a prebuilt ``AsyncOpenAI`` client.
"""

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from app.core.config import settings


def build_chat_model() -> OpenAIChatModel:
    client = AsyncOpenAI(
        api_key=settings.require_openrouter_api_key(),
        base_url=settings.openrouter_base_url,
    )
    return OpenAIChatModel(
        settings.chat_model,
        provider=OpenRouterProvider(openai_client=client),
    )
