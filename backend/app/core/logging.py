from __future__ import annotations

"""Logging setup for the backend application."""

import logging
import sys
from typing import Optional


def setup_logging(level: Optional[str] = "INFO") -> None:
    """Configure root logging with a concise format.

    Parameters
    ----------
    level: Optional[str]
        Log level name, e.g., "INFO", "DEBUG".
    """

    logging.basicConfig(
        level=getattr(logging, (level or "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

