from __future__ import annotations

"""Builds the LangGraph StateGraph and wires Redis-based checkpointing.

This is the central entrypoint for constructing the multi-node workflow.
Nodes are added here and edges defined using standard LangGraph patterns.
"""

from typing import Any
import os

from langgraph.graph import END, START, StateGraph  # type: ignore

from app.core.config import Settings, get_settings

from .memory.redis_checkpoint import get_checkpointer
from .nodes.llm_experts import (
    experts_finalize_node,
    experts_model_node,
    experts_tools_node,
)
from .nodes.router import router_node
from .nodes.security_analysis import security_analysis_node
from .nodes.static_analysis import static_analysis_node
from .nodes.synthesis import synthesis_node
from .state import CodeReviewState


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
    graph.add_node("static_analysis", static_analysis_node)
    graph.add_node("security_analysis", security_analysis_node)
    graph.add_node("experts_model", experts_model_node)
    graph.add_node("experts_tools", experts_tools_node)
    graph.add_node("experts_finalize", experts_finalize_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("persist", _persist_node)

    # Edges
    graph.add_edge(START, "router")
    graph.add_edge("router", "static_analysis")
    graph.add_edge("static_analysis", "security_analysis")
    graph.add_edge("security_analysis", "experts_model")

    # Conditional routing between model and tools, then finalize
    def _route_experts(state: dict[str, Any]) -> str:
        """Return the routing key for conditional edges.

        Must return the mapping key (e.g. "tools" or "finalize"), not the
        destination node id. LangGraph will look up the destination using the
        provided mapping in `add_conditional_edges`.
        """
        nxt = state.get("experts_next") or "finalize"
        if nxt == "tools":
            return "tools"
        return "finalize"

    graph.add_conditional_edges(
        "experts_model",
        _route_experts,
        {
            "tools": "experts_tools",
            "finalize": "experts_finalize",
        },
    )
    graph.add_edge("experts_tools", "experts_model")
    graph.add_edge("experts_finalize", "synthesis")
    graph.add_edge("synthesis", "persist")
    graph.add_edge("persist", END)

    # Checkpointer wiring (Redis preferred) – opt-in via env to simplify tests
    use_checkpointer = str(os.getenv("LANGGRAPH_CHECKPOINTER", "0")).lower() in {
        "1",
        "true",
        "yes",
    }
    if use_checkpointer:
        checkpointer = get_checkpointer(settings)
        app = graph.compile(checkpointer=checkpointer)
    else:
        app = graph.compile()
    return app
