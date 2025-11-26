from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from backend.models.state import CodeReviewState


def detect_language_node(state: dict[str, Any]) -> dict[str, Any]:
    code: str = state.get("code", "")
    lang = "python"
    if "import React" in code or ("function(" in code and "export default" in code):
        lang = "javascript"
    if "class " in code and "public static void main" in code:
        lang = "java"
    state["language"] = lang
    state["tool_logs"].append(
        {
            "id": "lang",
            "agent": "router",
            "message": f"Router: detected language = {lang}",
            "status": "completed",
        }
    )
    return state


def build_app() -> Any:
    """Construct and compile the LangGraph workflow for the MVP."""
    graph: StateGraph = StateGraph(CodeReviewState)

    graph.add_node("detect_language", detect_language_node)

    def persist_node(state: dict[str, Any]) -> dict[str, Any]:
        # Identity node used to checkpoint the final state under MemorySaver
        return state

    graph.add_node("persist", persist_node)

    graph.add_edge(START, "detect_language")
    graph.add_edge("detect_language", "persist")
    graph.add_edge("persist", END)

    return graph.compile(checkpointer=MemorySaver())
