from __future__ import annotations

"""Logging setup for the backend application.

Provides a simple, colored formatter for INFO/DEBUG/ERROR and helpers to
create module loggers consistently across the codebase.
"""

import logging
import os
import sys
from dataclasses import dataclass
from typing import Final

RESET: Final[str] = "\x1b[0m"
DIM: Final[str] = "\x1b[2m"
BOLD: Final[str] = "\x1b[1m"


@dataclass(frozen=True)
class _Palette:
    debug: str = "\x1b[36m"  # cyan
    info: str = "\x1b[32m"  # green
    warn: str = "\x1b[33m"  # yellow
    error: str = "\x1b[31m"  # red
    critical: str = "\x1b[41m\x1b[97m"  # white on red


class _ColorFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(fmt="%(message)s")
        self.palette = _Palette()

    def format(self, record: logging.LogRecord) -> str:
        lvl = record.levelno
        if lvl >= logging.CRITICAL:
            c = self.palette.critical
        elif lvl >= logging.ERROR:
            c = self.palette.error
        elif lvl >= logging.WARNING:
            c = self.palette.warn
        elif lvl >= logging.INFO:
            c = self.palette.info
        else:
            c = self.palette.debug

        time = self.formatTime(record, datefmt="%H:%M:%S")
        level = f"{c}{record.levelname:<7}{RESET}"
        name = f"{DIM}{record.name}{RESET}"
        msg = super().format(record)
        return f"{DIM}{time}{RESET} | {level} | {name} | {msg}"


def _color_enabled() -> bool:
    # Always color in terminals; allow opt-out via NO_COLOR
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()  # type: ignore[no-any-return]
    except Exception:
        return False


def setup_logging(level: str | None = "INFO") -> None:
    """Configure root logging with a concise, colored format.

    Parameters
    ----------
    level: Optional[str]
        Log level name, e.g., "INFO", "DEBUG".
    """

    # Reset existing handlers to avoid duplicate logs under reloaders
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    root.setLevel(getattr(logging, (level or "INFO").upper(), logging.INFO))
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(root.level)
    if _color_enabled():
        handler.setFormatter(_ColorFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger using the shared configuration."""
    return logging.getLogger(name)
