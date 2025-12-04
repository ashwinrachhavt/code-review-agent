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
from backend.graph.nodes.ast_tree_sitter import ast_tree_sitter_node
from backend.graph.nodes.chat_context_enrich import chat_context_enrich_node
from backend.graph.nodes.chat_reply import chat_reply_node
from backend.graph.nodes.collector import collector_node
from backend.graph.nodes.context import context_node
from backend.graph.nodes.router import router_node
from backend.graph.nodes.specialists.api_expert_llm import api_expert_node
from backend.graph.nodes.specialists.db_expert_llm import db_expert_node
from backend.graph.nodes.specialists.security_expert_llm import security_expert_node
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
    graph.add_node("build_context", context_node)
    graph.add_node("tools_parallel", tools_parallel_node)

    # Expert LLM nodes (run in parallel after tools)
    graph.add_node("security_expert", security_expert_node)
    graph.add_node("api_expert", api_expert_node)
    graph.add_node("db_expert", db_expert_node)

    # AST analysis (also runs in parallel)
    graph.add_node("ast_analysis", ast_tree_sitter_node)

    # Collector merges expert outputs
    graph.add_node("collector", collector_node)

    graph.add_node("synthesis", synthesis_node)
    graph.add_node("persist", _persist_node)

    # Chat nodes
    graph.add_node("chat_context_enrich", chat_context_enrich_node)
    graph.add_node("chat_reply", chat_reply_node)

    # Edges
    # Mode gate: route to chat or full analysis
    def _mode_gate(state: dict[str, Any]) -> dict[str, Any]:
        return state

    def _route_mode(state: dict[str, Any]) -> str:
        mode = str(state.get("mode") or "").lower()
        return "chat" if mode == "chat" else "analyze"

    graph.add_node("mode_gate", _mode_gate)
    graph.add_edge(START, "mode_gate")
    graph.add_conditional_edges(
        "mode_gate",
        _route_mode,
        {
            "chat": "chat_context_enrich",
            "analyze": "router",
        },
    )

    # Chat path: enrich context then reply
    graph.add_edge("chat_context_enrich", "chat_reply")

    graph.add_edge("router", "build_context")
    graph.add_edge("build_context", "tools_parallel")

    # Parallel expert execution after tools
    graph.add_edge("tools_parallel", "security_expert")
    graph.add_edge("tools_parallel", "api_expert")
    graph.add_edge("tools_parallel", "db_expert")
    graph.add_edge("tools_parallel", "ast_analysis")

    # Collector waits for all experts + AST
    graph.add_edge("security_expert", "collector")
    graph.add_edge("api_expert", "collector")
    graph.add_edge("db_expert", "collector")
    graph.add_edge("ast_analysis", "collector")

    # Then synthesis
    graph.add_edge("collector", "synthesis")
    graph.add_edge("synthesis", "persist")
    graph.add_edge("chat_reply", "persist")
    graph.add_edge("persist", END)

    # Checkpointer wiring (SQLite preferred) - opt-in via env to simplify tests
    use_checkpointer = str(os.getenv("LANGGRAPH_CHECKPOINTER", "0")).lower() in {
        "1",
        "true",
        "yes",
    }
    if use_checkpointer:
        # Prefer a safe in-memory checkpointer unless explicitly overridden.
        backend_pref = str(os.getenv("LANGGRAPH_CHECKPOINTER_BACKEND", "memory")).lower()
        try:
            if backend_pref == "sqlite":
                cp = get_checkpointer(settings.DATABASE_URL)
            else:
                from langgraph.checkpoint.memory import MemorySaver  # type: ignore

                cp = MemorySaver()
            # Guard against misconfigured backends returning context managers
            if not hasattr(cp, "get_next_version"):
                from langgraph.checkpoint.memory import MemorySaver  # type: ignore

                cp = MemorySaver()
            app = graph.compile(checkpointer=cp)
        except Exception:
            app = graph.compile()
    else:
        app = graph.compile()
    return app
