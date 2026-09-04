"""Embedding client shared by the offline ingest pipeline and the online retriever.

Both sides must embed into the same pgvector column with the same model, so the
client, the batching and the width check live here rather than in either caller.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache

from openai import AsyncOpenAI

from app.core.config import settings

# OpenRouter's free tier throttles hard on larger batches
EMBED_BATCH_SIZE = 100

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]


@lru_cache
def _client() -> AsyncOpenAI:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for embeddings")
    return AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


async def get_embedding(texts: list[str]) -> list[list[float]]:
    """Embed ``texts`` with the configured model, one vector per input."""
    client = _client()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
            dimensions=settings.embedding_dimensions,
            # the OpenAI SDK defaults to base64, which OpenRouter's upstream
            # providers reject outright
            encoding_format="float",
        )
        for item in response.data:
            # OpenRouter routes `:free` models by load, so upstream providers
            # disagree on width even when `dimensions` is sent. Check rather
            # than trust: a wrong width would poison the pgvector column.
            if len(item.embedding) != settings.embedding_dimensions:
                raise ValueError(
                    f"unexpected embedding dimension {len(item.embedding)}, "
                    f"expected {settings.embedding_dimensions}"
                )
            vectors.append(item.embedding)
    return vectors
