from __future__ import annotations

"""Lightweight optional Redis JSON cache.

If `redis` is not installed or `REDIS_URL` is unset, functions become no-ops.
"""

from typing import Any
import json
import os

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

try:  # pragma: no cover - optional dependency
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore


_client = None


def get_redis_client():
    global _client
    if _client is not None:
        return _client
    if redis is None:
        return None
    url = (os.getenv("REDIS_URL") or get_settings().REDIS_URL or "").strip()
    if not url:
        return None
    try:
        _client = redis.Redis.from_url(url, decode_responses=True)
        # ping once
        _client.ping()
        return _client
    except Exception:
        logger.debug("Redis unavailable at %s; disabling cache", url)
        _client = None
        return None


def cache_get_json(key: str) -> Any | None:
    client = get_redis_client()
    if client is None:
        return None
    try:
        data = client.get(key)
        if not data:
            return None
        return json.loads(data)
    except Exception:
        return None


def cache_set_json(key: str, value: Any, ttl_seconds: int = 30) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        payload = json.dumps(value)
        client.set(key, payload, ex=ttl_seconds)
    except Exception:
        pass


def cache_delete(key: str) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        client.delete(key)
    except Exception:
        pass


def cache_delete_prefix(prefix: str) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor=cursor, match=f"{prefix}*", count=100)
            if keys:
                client.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        pass

