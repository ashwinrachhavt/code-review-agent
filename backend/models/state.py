from typing import Any, TypedDict


class CodeReviewState(TypedDict, total=False):
    """Shared state for the LangGraph workflow.

    This keeps the MVP small while leaving room for expansion.
    """

    # Core input
    code: str
    language: str | None

    # Expert outputs
    security_report: dict[str, Any] | None
    quality_report: dict[str, Any] | None
    bug_report: dict[str, Any] | None

    # Synthesis
    final_report: str | None

    # UX helpers (optional for richer UI later)
    tool_logs: list[dict[str, Any]]
    progress: float
