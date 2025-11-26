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
        Redis URL used for LangGraph checkpointing and semantic cache.
    REDIS_NAMESPACE: str
        Namespace/prefix used for keys in Redis.
    LOG_LEVEL: str
        Application log level.
    USE_CELERY: bool
        Whether to offload graph execution to Celery workers.
    CELERY_BROKER_URL: str
        Celery broker URL (defaults to REDIS_URL).
    CELERY_RESULT_BACKEND: str
        Celery result backend URL (defaults to REDIS_URL).
    """

    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Redis configuration (checkpointer + semantic cache)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_NAMESPACE: str = os.getenv("REDIS_NAMESPACE", "code-review-agent")

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Celery integration (optional)
    USE_CELERY: bool = os.getenv("USE_CELERY", "0").lower() in {"1", "true", "yes"}
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return memoized Settings instance.

    Returns
    -------
    Settings
        The global application settings.
    """

    return Settings()
