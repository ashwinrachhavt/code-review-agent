from __future__ import annotations

"""Semantic cache interface and Redis-backed implementation.

Design goals:
- Generic interface that stores arbitrary JSON-serializable values.
- Embeddings from OpenAI when available; otherwise a lightweight local embedder.
- Redis backend preferred; fallback to in-memory store.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import Settings, get_settings


# -------------------- Embedders --------------------


class Embedder(ABC):
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Return a float vector embedding for the given text."""


class LocalEmbedder(Embedder):
    """A tiny, dependency-free locality-sensitive embedder.

    Uses hashed 3-gram character features into 256 buckets, L2-normalized.
    Not a true semantic model, but provides stability and rough similarity.
    """

    def __init__(self, dims: int = 256) -> None:
        self.dims = dims

    def embed(self, text: str) -> List[float]:
        text = (text or "").lower()
        vec = [0.0] * self.dims
        if len(text) < 3:
            return vec
        for i in range(len(text) - 2):
            tri = text[i : i + 3]
            h = hash(tri) % self.dims
            vec[h] += 1.0
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class OpenAIEmbedder(Embedder):  # pragma: no cover - network-dependent
    def __init__(self, model: Optional[str] = None) -> None:
        # Prefer text-embedding-3-small for cost-efficiency
        self.model = model or os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        try:
            from langchain_openai import OpenAIEmbeddings  # type: ignore
        except Exception as e:
            raise RuntimeError("langchain-openai not available for embeddings") from e
        self._client = OpenAIEmbeddings(model=self.model)

    def embed(self, text: str) -> List[float]:
        return list(self._client.embed_query(text))  # type: ignore[no-any-return]


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


# -------------------- Cache Interface --------------------


class SemanticCache(ABC):
    @abstractmethod
    def get(self, query: str, namespace: str, *, min_score: float = 0.92) -> Optional[Dict[str, Any]]:
        """Return the closest cached value if similarity >= min_score.

        Returns a dict with at least: {"score": float, "value": Any}
        or None if no match.
        """

    @abstractmethod
    def set(self, query: str, value: Any, namespace: str) -> None:
        """Store the value for the given query under the namespace."""


@dataclass
class CacheItem:
    key: str
    embedding: List[float]
    value: Any
    ts: float


class MemorySemanticCache(SemanticCache):
    """In-memory semantic cache (per-process)."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self.store: Dict[str, Dict[str, CacheItem]] = {}

    def _ns(self, namespace: str) -> Dict[str, CacheItem]:
        return self.store.setdefault(namespace, {})

    def get(self, query: str, namespace: str, *, min_score: float = 0.92) -> Optional[Dict[str, Any]]:
        ns = self._ns(namespace)
        if not ns:
            return None
        qv = self.embedder.embed(query)
        best: Tuple[Optional[str], float] = (None, 0.0)
        for key, item in ns.items():
            s = cosine(qv, item.embedding)
            if s > best[1]:
                best = (key, s)
        if best[0] is None or best[1] < float(min_score):
            return None
        item = ns[best[0]]
        return {"score": best[1], "value": item.value}

    def set(self, query: str, value: Any, namespace: str) -> None:
        ns = self._ns(namespace)
        key = f"{hash(query)}:{int(time.time())}"
        emb = self.embedder.embed(query)
        ns[key] = CacheItem(key=key, embedding=emb, value=value, ts=time.time())
        # Simple cap to avoid unbounded growth
        if len(ns) > 512:
            # Remove oldest
            oldest = sorted(ns.values(), key=lambda x: x.ts)[:64]
            for it in oldest:
                ns.pop(it.key, None)


class RedisSemanticCache(SemanticCache):  # pragma: no cover - external service
    """Redis-backed semantic cache.

    Stores entries as hashes under: {namespace}:{id}
    Maintains a set of keys under: {namespace}:keys
    Performs client-side similarity search over namespace keys.
    """

    def __init__(self, embedder: Embedder, redis_client: Any, namespace: str) -> None:
        self.embedder = embedder
        self.r = redis_client
        self.namespace = namespace

    def _ns_keys_key(self, namespace: str) -> str:
        return f"sc:{namespace}:keys"

    def _item_key(self, namespace: str, item_id: str) -> str:
        return f"sc:{namespace}:{item_id}"

    def get(self, query: str, namespace: str, *, min_score: float = 0.92) -> Optional[Dict[str, Any]]:
        import json as _json

        keys_key = self._ns_keys_key(namespace)
        ids = self.r.smembers(keys_key) or []
        ids = [i.decode("utf-8") if isinstance(i, bytes) else str(i) for i in ids]
        if not ids:
            return None
        qv = self.embedder.embed(query)
        best: Tuple[Optional[str], float] = (None, 0.0)
        for item_id in ids:
            raw = self.r.hgetall(self._item_key(namespace, item_id)) or {}
            emb_s = raw.get(b"embedding") or raw.get("embedding")
            if not emb_s:
                continue
            try:
                emb = _json.loads(emb_s if isinstance(emb_s, str) else emb_s.decode("utf-8"))
            except Exception:
                continue
            s = cosine(qv, emb)
            if s > best[1]:
                best = (item_id, s)
        if best[0] is None or best[1] < float(min_score):
            return None
        raw = self.r.hgetall(self._item_key(namespace, best[0])) or {}
        val_s = raw.get(b"value") or raw.get("value")
        try:
            val = _json.loads(val_s if isinstance(val_s, str) else (val_s.decode("utf-8") if val_s else "null"))
        except Exception:
            val = None
        return {"score": best[1], "value": val}

    def set(self, query: str, value: Any, namespace: str) -> None:
        import json as _json
        import time as _time

        emb = self.embedder.embed(query)
        item_id = f"{abs(hash(query))}:{int(_time.time())}"
        key = self._item_key(namespace, item_id)
        self.r.hset(
            key,
            mapping={
                "embedding": _json.dumps(emb),
                "value": _json.dumps(value),
            },
        )
        self.r.sadd(self._ns_keys_key(namespace), item_id)


# -------------------- Factory --------------------


def _get_embedder(settings: Settings) -> Embedder:
    if settings.OPENAI_API_KEY:
        try:
            return OpenAIEmbedder()
        except Exception:
            pass
    return LocalEmbedder()


def get_semantic_cache(settings: Optional[Settings] = None) -> SemanticCache:
    settings = settings or get_settings()
    embedder = _get_embedder(settings)

    try:
        import redis  # type: ignore

        # If no redis installed or connection fails, fall back to memory cache
        client = redis.from_url(settings.REDIS_URL, decode_responses=False)
        # ping to ensure connectivity
        try:
            client.ping()
        except Exception:
            return MemorySemanticCache(embedder)
        return RedisSemanticCache(embedder, client, settings.REDIS_NAMESPACE)
    except Exception:
        return MemorySemanticCache(embedder)


# -------------------- Helpers --------------------


def build_query_string(*parts: str, max_len: int = 4000) -> str:
    """Build a canonical query string truncated to a safe length."""
    base = "|".join(p for p in parts if p)
    return base[:max_len]

