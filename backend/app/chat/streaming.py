import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress


def answer_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def with_heartbeat(
    events: AsyncIterator[str], interval: float = 15
) -> AsyncIterator[str]:
    iterator = events.__aiter__()
    pending: asyncio.Task[str] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(iterator))
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield ": ping\n\n"
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                pending = None
                break
            pending = None
            yield event
    finally:
        if pending is not None:
            pending.cancel()
            with suppress(asyncio.CancelledError):
                await pending
        await events.aclose()
