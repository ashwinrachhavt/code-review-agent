from __future__ import annotations

"""Central application configuration.

This module provides a single Settings object for environment-driven
configuration. Keep it lightweight (no extra deps like pydantic-settings).
"""

from dataclasses import dataclass
from functools import lru_cache
import os
from typing import Optional


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
    """

    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Redis configuration (checkpointer + semantic cache)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_NAMESPACE: str = os.getenv("REDIS_NAMESPACE", "code-review-agent")

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

