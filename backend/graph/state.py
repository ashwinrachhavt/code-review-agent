from __future__ import annotations

"""Strongly-typed shared state for LangGraph.

The state is designed to be serializable by LangGraph's checkpointing layer
and resilient to partial updates from nodes. Keep values JSON-serializable.
"""

from typing import Any, Dict, List, Optional, TypedDict


class HistoryMessage(TypedDict, total=False):
    role: str
    content: str


class CodeReviewState(TypedDict, total=False):
    """Shared state carried across the LangGraph workflow.

    Fields are optional (total=False) to allow incremental population by nodes.
    """

    # Core input
    code: str
    language: Optional[str]

    # Conversation memory
    history: List[HistoryMessage]

    # Expert outputs
    quality_report: Optional[Dict[str, Any]]
    bug_report: Optional[Dict[str, Any]]
    security_report: Optional[Dict[str, Any]]

    # Tooling + orchestration metadata
    tool_logs: List[Dict[str, Any]]
    progress: float
    mode: str
    agents: List[str]

    # Synthesis result
    final_report: Optional[str]

    # Agent tool-calling scratchpad (internal to experts loop)
    agent_messages: List[Any]
    experts_iterations: int


def initial_state(
    *,
    code: str,
    history: Optional[List[HistoryMessage]] = None,
    mode: str = "orchestrator",
    agents: Optional[List[str]] = None,
) -> CodeReviewState:
    """Construct an initial state with safe defaults.

    Parameters
    ----------
    code: str
        Source code snippet or file content to analyze.
    history: Optional[List[HistoryMessage]]
        Recent conversation history (optional).
    mode: str
        Orchestration mode (e.g., "orchestrator" or "specialists").
    agents: Optional[List[str]]
        Selected agents to run (quality, bug, security).

    Returns
    -------
    CodeReviewState
        Initial state mapping
    """

    return {
        "code": code,
        "language": None,
        "history": list(history or [])[-20:],
        "quality_report": None,
        "bug_report": None,
        "security_report": None,
        "tool_logs": [],
        "progress": 0.0,
        "mode": mode,
        "agents": agents or ["quality", "bug", "security"],
        "final_report": None,
    }
