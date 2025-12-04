from __future__ import annotations

"""Prompt loader for system/agent instructions stored as Markdown files.

Loads prompts from files alongside this module with simple LRU caching.
"""

from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR


@lru_cache(maxsize=64)
def get_prompt(name: str) -> str | None:
    """Load a prompt template by name.

    Parameters
    ----------
    name: str
        Prompt name (e.g., 'synthesis_system' or 'specialists/security')

    Returns
    -------
    Optional[str]
        Prompt content or None if not found
    """

    # Support both .md files and without extension
    if not name.endswith(".md"):
        name = f"{name}.md"

    prompt_path = PROMPTS_DIR / name
    if not prompt_path.exists():
        return None

    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception:  # pragma: no cover
        return None
