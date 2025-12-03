from __future__ import annotations

"""Optional SQLAlchemy engine/session helpers.

This module centralizes DB setup behind small helpers. It is not used by
default; routes and graph run with in-memory state. Callers may import these
helpers when enabling persistence.
"""

from pathlib import Path
from typing import Any

from backend.app.core.config import Settings, get_settings

try:  # optional SQLAlchemy
    from sqlalchemy import create_engine  # type: ignore
    from sqlalchemy.orm import sessionmaker  # type: ignore

    _SA_AVAILABLE = True
except Exception:  # pragma: no cover
    create_engine = None  # type: ignore
    sessionmaker = None  # type: ignore
    _SA_AVAILABLE = False


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite:///"):
        # sqlite:///relative/path.db
        rel = url.removeprefix("sqlite:///")
        p = Path(rel).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)


def get_engine(settings: Settings | None = None) -> Any:
    """Return SQLAlchemy engine if available; raises if not installed."""
    if not _SA_AVAILABLE:
        raise RuntimeError("SQLAlchemy not installed; install to enable DB persistence")
    settings = settings or get_settings()
    url = settings.DATABASE_URL
    _ensure_sqlite_dir(url)
    return create_engine(url, future=True)


def get_sessionmaker(engine: Any | None = None) -> Any:
    """Return a sessionmaker bound to the given engine or default engine."""
    if not _SA_AVAILABLE:
        raise RuntimeError("SQLAlchemy not installed; install to enable DB persistence")
    eng = engine or get_engine()
    return sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
