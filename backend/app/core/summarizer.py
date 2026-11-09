from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache

from openai import AsyncOpenAI

from app.core.config import settings

SummarizeFn = Callable[[str], Awaitable[str]]

_SYSTEM_PROMPT = (
    "You summarize SEC filings for a retrieval index. Given the markdown of one "
    "filing, write a single concise paragraph (under 200 words) covering the "
    "company, reporting period, key financial figures, major risks, and the main "
    "topics each section discusses. Output only the summary text."
)


@lru_cache
def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.require_openrouter_api_key(),
        base_url=settings.openrouter_base_url,
    )


async def get_summary(markdown: str) -> str:
    response = await _client().chat.completions.create(
        model=settings.summary_model or settings.chat_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": markdown[: settings.summary_max_input_chars]},
        ],
    )
    summary = (response.choices[0].message.content or "").strip()
    if not summary:
        raise ValueError("LLM returned an empty summary")
    return summary
