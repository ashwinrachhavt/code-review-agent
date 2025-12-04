from __future__ import annotations

"""SQLite-backed LangGraph checkpointer.

Falls back to in-memory checkpoints if the sqlite saver is unavailable.
"""

from typing import Any
import os

from backend.app.core.logging import get_logger

logger = get_logger(__name__)

try:
    from langgraph.checkpoint.memory import MemorySaver  # type: ignore
except Exception:  # pragma: no cover - should be available in base package
    MemorySaver = None  # type: ignore

try:
    # Requires `pip install langgraph-checkpoint-sqlite` or `langgraph[checkpoint-sqlite]`
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    SqliteSaver = None  # type: ignore


def get_checkpointer(db_path: str) -> Any:
    """Return a checkpointer using SQLite when available.

    Parameters
    ----------
    db_path: str
        Path or connection string for SQLite storage. If SqliteSaver supports
        connection strings, we'll pass it; otherwise, we try as a file path.
    """

    if SqliteSaver is not None:
        # Normalize sqlite URL to path if needed
        conn = str(db_path)
        try:
            # Prefer from_conn_string when available
            if hasattr(SqliteSaver, "from_conn_string"):
                cp = SqliteSaver.from_conn_string(conn)  # type: ignore[attr-defined]
            else:
                # If given sqlite:///path convert to FS path
                if conn.startswith("sqlite:///"):
                    fs_path = conn.replace("sqlite:///", "", 1)
                else:
                    fs_path = conn
                cp = SqliteSaver(fs_path)  # type: ignore[call-arg]
            # Guard: ensure we return a real saver, not a context manager
            if not hasattr(cp, "get_next_version"):
                raise TypeError("SqliteSaver did not return a Saver instance")
            return cp
        except Exception as e:
            logger.debug("SqliteSaver init failed (%s); using in-memory checkpointer", e)
    else:
        logger.info(
            "SQLite checkpointer not installed; install 'langgraph-checkpoint-sqlite' to enable persistence"
        )
    if MemorySaver is None:  # pragma: no cover
        raise RuntimeError("No available LangGraph checkpointer backend found.")
    return MemorySaver()
