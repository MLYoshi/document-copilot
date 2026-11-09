from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache

from openai import AsyncOpenAI

from app.core.config import settings

EMBED_BATCH_SIZE = 100

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]


@lru_cache
def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.require_openrouter_api_key(),
        base_url=settings.openrouter_base_url,
    )


async def get_embedding(texts: list[str]) -> list[list[float]]:
    client = _client()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
            dimensions=settings.embedding_dimensions,
            encoding_format="float",
        )
        for item in response.data:
            if len(item.embedding) != settings.embedding_dimensions:
                raise ValueError(
                    f"unexpected embedding dimension {len(item.embedding)}, "
                    f"expected {settings.embedding_dimensions}"
                )
            vectors.append(item.embedding)
    return vectors
