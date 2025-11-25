from __future__ import annotations

"""Prompt loader for system/agent instructions stored as Markdown files.

Loads prompts from files alongside this module with simple LRU caching.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=64)
def get_prompt(name: str) -> str:
    """Return the Markdown content for a named prompt.

    Parameters
    ----------
    name: str
        Base filename without extension, e.g., "synthesis_system".

    Returns
    -------
    str
        Full Markdown content. Returns an empty string if not found.
    """

    path = BASE_DIR / f"{name}.md"
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

