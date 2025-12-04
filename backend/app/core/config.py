from __future__ import annotations

"""Central application configuration.

This module provides a single Settings object for environment-driven
configuration. Keep it lightweight (no extra deps like pydantic-settings).
"""

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables.

    Attributes
    ----------
    OPENAI_API_KEY: Optional[str]
        API key for OpenAI. Optional to allow running without synthesis.
    OPENAI_MODEL: str
        Default OpenAI chat model for synthesis/expert nodes.
    REDIS_URL: str
        Redis URL (legacy; kept for backward compatibility only).
    REDIS_NAMESPACE: str
        Legacy Redis namespace; unused when SQLite is enabled.
    DATABASE_URL: str
        SQLAlchemy connection string for SQLite (default: sqlite:///backend/data.db).
    QDRANT_PATH: str
        Qdrant local path or ":memory:" for in-memory vector DB.
    QDRANT_MIN_FILES: int
        Minimal file count threshold to trigger vector indexing.
    QDRANT_MIN_BYTES: int
        Minimal total bytes threshold to trigger vector indexing.
    LOG_LEVEL: str
        Application log level.
    # Note: Celery support has been removed.
    """

    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_NAMESPACE: str = os.getenv("REDIS_NAMESPACE", "code-review-agent")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///backend/data.db")
    QDRANT_PATH: str = os.getenv("QDRANT_PATH", ":memory:")
    QDRANT_MIN_FILES: int = int(os.getenv("QDRANT_MIN_FILES", "10"))
    QDRANT_MIN_BYTES: int = int(os.getenv("QDRANT_MIN_BYTES", "100000"))

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return memoized Settings instance.

    Returns
    -------
    Settings
        The global application settings.
    """

    return Settings()
