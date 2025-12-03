from __future__ import annotations

"""SQLite-backed LangGraph checkpointer.

Falls back to in-memory checkpoints if the sqlite saver is unavailable.
"""

from typing import Any

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
        # Try both APIs for robustness across langgraph versions
        try:
            # Newer versions may provide from_conn_string
            if hasattr(SqliteSaver, "from_conn_string"):
                return SqliteSaver.from_conn_string(db_path)  # type: ignore[attr-defined]
        except Exception:
            logger.debug("SqliteSaver.from_conn_string failed; falling back to direct init")
        try:
            # Fallback: pass file path directly
            return SqliteSaver(db_path)  # type: ignore[call-arg]
        except Exception:
            logger.debug("SqliteSaver direct init failed; using in-memory checkpointer")
    else:
        logger.info(
            "SQLite checkpointer not installed; install 'langgraph-checkpoint-sqlite' to enable persistence"
        )
    if MemorySaver is None:  # pragma: no cover
        raise RuntimeError("No available LangGraph checkpointer backend found.")
    return MemorySaver()
