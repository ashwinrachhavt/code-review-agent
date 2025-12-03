from __future__ import annotations

"""SQLite-backed LangGraph checkpointer.

Falls back to in-memory checkpoints if the sqlite saver is unavailable.
"""

from typing import Any

try:
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore
except Exception:  # pragma: no cover
    SqliteSaver = None  # type: ignore

try:
    from langgraph.checkpoint.memory import MemorySaver  # type: ignore
except Exception:  # pragma: no cover
    MemorySaver = None  # type: ignore


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
            pass
        try:
            # Fallback: pass file path directly
            return SqliteSaver(db_path)  # type: ignore[call-arg]
        except Exception:
            pass
    if MemorySaver is None:  # pragma: no cover
        raise RuntimeError("No available LangGraph checkpointer backend found.")
    return MemorySaver()
