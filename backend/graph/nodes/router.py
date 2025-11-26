from __future__ import annotations

"""Language router node.

Detects the code language and logs the routing decision.
"""

from typing import Any


def router_node(state: dict[str, Any]) -> dict[str, Any]:
    """Detect language from the code and update progress.

    Parameters
    ----------
    state: Dict[str, Any]
        Shared graph state.

    Returns
    -------
    Dict[str, Any]
        Updated state with `language` set and a router log entry.
    """

    code: str = state.get("code", "") or ""
    lang = "python"
    if ("import React" in code) or ("function(" in code and "export default" in code):
        lang = "javascript"
    if ("class " in code) and ("public static void main" in code):
        lang = "java"

    state["language"] = lang
    logs = state.get("tool_logs") or []
    logs.append(
        {
            "id": "router",
            "agent": "router",
            "message": f"Router: detected language = {lang}",
            "status": "completed",
        }
    )
    state["tool_logs"] = logs
    state["progress"] = min(100.0, float(state.get("progress", 0.0)) + 5.0)
    return state
