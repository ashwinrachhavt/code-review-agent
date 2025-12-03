from __future__ import annotations

"""Strongly-typed shared state for LangGraph.

The state is designed to be serializable by LangGraph's checkpointing layer
and resilient to partial updates from nodes. Keep values JSON-serializable.
"""

from typing import Annotated, Any, TypedDict

try:
    # Preferred message reducer for conversation histories
    from langgraph.graph.message import add_messages  # type: ignore
except Exception:  # pragma: no cover

    def add_messages(x, y):  # type: ignore
        return (x or []) + (y or [])


class HistoryMessage(TypedDict, total=False):
    role: str
    content: str


class CodeReviewState(TypedDict, total=False):
    """Shared state carried across the LangGraph workflow.

    Fields are optional (total=False) to allow incremental population by nodes.
    """

    # Core input
    code: str
    language: str | None
    source: str | None
    files: list[dict[str, Any]]

    # Conversation memory
    history: list[HistoryMessage]
    messages: Annotated[list[Any], add_messages]

    # Expert outputs
    quality_report: dict[str, Any] | None
    bug_report: dict[str, Any] | None
    security_report: dict[str, Any] | None
    ast_report: dict[str, Any] | None
    context: dict[str, Any] | None

    # Tooling + orchestration metadata
    tool_logs: list[dict[str, Any]]
    progress: float
    mode: str
    agents: list[str]

    # Synthesis result
    final_report: str | None

    # Agent tool-calling scratchpad (internal to experts loop)
    agent_messages: list[Any]
    experts_iterations: int

    # Input modality + context
    input_mode: str  # 'paste' | 'folder' | 'repo'
    folder_path: str | None
    code_context: dict[str, str]
    vectorstore_id: str | None


def initial_state(
    *,
    code: str,
    history: list[HistoryMessage] | None = None,
    mode: str = "orchestrator",
    agents: list[str] | None = None,
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
        "messages": [],
        "quality_report": None,
        "bug_report": None,
        "security_report": None,
        "tool_logs": [],
        "progress": 0.0,
        "mode": mode,
        "agents": agents or ["quality", "bug", "security"],
        "final_report": None,
        "input_mode": "paste",
        "folder_path": None,
        "code_context": {},
        "vectorstore_id": None,
    }
