from __future__ import annotations

"""Redis-backed checkpointer wiring for LangGraph.

Falls back to in-memory checkpoints if Redis is unavailable. The Redis saver
ensures per-thread resumability using LangGraph's `thread_id` concept.
"""

from typing import Any

from app.core.config import Settings

try:  # Prefer RedisSaver when available
    from langgraph.checkpoint.redis import RedisSaver  # type: ignore
except Exception:  # pragma: no cover
    RedisSaver = None  # type: ignore

try:
    from langgraph.checkpoint.memory import MemorySaver  # type: ignore
except Exception:  # pragma: no cover
    MemorySaver = None  # type: ignore


def get_checkpointer(settings: Settings) -> Any:
    """Return a checkpointer instance using Redis if possible.

    Parameters
    ----------
    settings: Settings
        Application settings containing Redis connection info.

    Returns
    -------
    Any
        A LangGraph checkpointer (RedisSaver or MemorySaver).
    """

    if RedisSaver is not None:
        # RedisSaver supports namespaces to isolate apps
        return RedisSaver.from_conn_info(
            settings.REDIS_URL,
            namespace=settings.REDIS_NAMESPACE,
        )
    # Graceful fallback (non-persistent)
    if MemorySaver is None:  # pragma: no cover
        raise RuntimeError("No available LangGraph checkpointer backend found.")
    return MemorySaver()

