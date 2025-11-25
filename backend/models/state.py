from typing import Any, Dict, List, Optional, TypedDict


class CodeReviewState(TypedDict, total=False):
    """Shared state for the LangGraph workflow.

    This keeps the MVP small while leaving room for expansion.
    """

    # Core input
    code: str
    language: Optional[str]

    # Expert outputs
    security_report: Optional[Dict[str, Any]]
    quality_report: Optional[Dict[str, Any]]
    bug_report: Optional[Dict[str, Any]]

    # Synthesis
    final_report: Optional[str]

    # UX helpers (optional for richer UI later)
    tool_logs: List[Dict[str, Any]]
    progress: float

