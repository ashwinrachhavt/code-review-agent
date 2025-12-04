from __future__ import annotations

"""Qdrant service helper.

Provides a singleton local Qdrant client for in-memory (default) or file-backed collections.
"""

from functools import lru_cache

from backend.app.core.config import get_settings
from qdrant_client import QdrantClient  # type: ignore


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    s = get_settings()
    path = s.QDRANT_PATH
    # Use local mode; ":memory:" creates an ephemeral DB
    return QdrantClient(path=path)


def collection_name_for_thread(thread_id: str) -> str:
    return f"code-review-{thread_id}".replace("/", "-")[:64]
