from __future__ import annotations

"""Redis pub/sub helpers for SSE streaming."""

import asyncio
from typing import AsyncGenerator
import contextlib


async def pubsub_messages(redis_url: str, channel: str, *, poll_interval: float = 0.5) -> AsyncGenerator[str, None]:
    """Yield messages from a Redis pub/sub channel.

    This function uses a background thread via asyncio.to_thread to call
    blocking redis-py methods without requiring an async Redis client.
    """

    import redis  # type: ignore

    r = redis.from_url(redis_url, decode_responses=True)
    ps = r.pubsub(ignore_subscribe_messages=True)
    ps.subscribe(channel)

    try:
        while True:
            # Use get_message with timeout in a thread to avoid blocking loop
            msg = await asyncio.to_thread(ps.get_message, timeout=poll_interval)
            if msg and msg.get("type") == "message":
                data = msg.get("data")
                if isinstance(data, str):
                    yield data
                    if data.strip() == ":::done":
                        break
            await asyncio.sleep(0)  # allow cancellation
    finally:
        with contextlib.suppress(Exception):
            ps.unsubscribe(channel)
            ps.close()
