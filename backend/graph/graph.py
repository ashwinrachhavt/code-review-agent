from __future__ import annotations

"""Builds the LangGraph StateGraph and wires Redis-based checkpointing.

This is the central entrypoint for constructing the multi-node workflow.
Nodes are added here and edges defined using standard LangGraph patterns.
"""

import os
from typing import Any

from langgraph.graph import END, START, StateGraph  # type: ignore

from backend.app.core.config import Settings, get_settings
from backend.graph.memory.sqlite_checkpoint import get_checkpointer
from backend.graph.nodes.chat_mode import chat_mode_node
from backend.graph.nodes.router import router_node
from backend.graph.nodes.synthesis import synthesis_node
from backend.graph.nodes.tools_parallel import tools_parallel_node
from backend.graph.state import CodeReviewState


def _persist_node(state: dict[str, Any]) -> dict[str, Any]:
    """Identity node to create a checkpoint barrier at the end.

    Useful during early phases to ensure thread persistence works even before
    we add the full set of nodes.
    """

    return state


def build_graph(settings: Settings | None = None) -> Any:
    """Construct and compile the LangGraph workflow.

    The compiled graph includes a Redis-backed checkpointer (falling back to
    in-memory if Redis is unavailable), enabling per-thread resumability.

    Parameters
    ----------
    settings: Settings | None
        Optional settings; if omitted, global settings are used.

    Returns
    -------
    Any
        A compiled LangGraph application ready for `invoke` / `astream`.
    """

    settings = settings or get_settings()

    graph: StateGraph[CodeReviewState] = StateGraph(CodeReviewState)

    # Nodes
    graph.add_node("router", router_node)
    graph.add_node("tools_parallel", tools_parallel_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("chat_mode", chat_mode_node)
    graph.add_node("persist", _persist_node)

    # Edges
    graph.add_edge(START, "router")
    graph.add_edge("router", "chat_mode")
    graph.add_edge("chat_mode", "tools_parallel")
    graph.add_edge("tools_parallel", "synthesis")
    graph.add_edge("synthesis", "persist")
    graph.add_edge("persist", END)

    # Checkpointer wiring (SQLite preferred) - opt-in via env to simplify tests
    use_checkpointer = str(os.getenv("LANGGRAPH_CHECKPOINTER", "0")).lower() in {
        "1",
        "true",
        "yes",
    }
    if use_checkpointer:
        # Use SQLite checkpointer with the app database path
        db_url = settings.DATABASE_URL
        # LangGraph sqlite saver may accept file path; extract path from URL if possible
        db_path = db_url
        if db_url.startswith("sqlite:///"):
            db_path = db_url[len("sqlite:///") :]
        checkpointer = get_checkpointer(db_path)
        app = graph.compile(checkpointer=checkpointer)
    else:
        app = graph.compile()
    return app
